import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from flask import Flask, current_app
from flask_migrate import upgrade
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import ORMExecuteState, Session as SQLAlchemySession


db = SQLAlchemy()

_TABLAS_PROTEGIDAS_HISTORICAS = {
    "tutor",
    "usuario",
    "alumno",
    "anio_lectivo",
    "matricula",
    "historial_grupo_matricula",
    "ciclo_escolar",
    "aspirante_crm",
    "calificacion",
    "intento_calificacion",
    "inscripcion_materia",
    "asistencia",
    "notificacion_asistencia",
    "certificado_medico",
    "factura",
    "detalle_factura",
    "curso_direccion",
}

_TABLAS_APPEND_ONLY = {"evento_auditoria", "notificacion_asistencia"}


@event.listens_for(SQLAlchemySession, "before_flush")
def impedir_borrado_fisico(
    session: SQLAlchemySession,
    flush_context: object,
    instances: object,
) -> None:
    for registro in session.deleted:
        tabla = getattr(type(registro), "__tablename__", None)
        if tabla in _TABLAS_APPEND_ONLY:
            raise ValueError("Los eventos de auditoría no se pueden borrar.")
        if tabla in _TABLAS_PROTEGIDAS_HISTORICAS:
            raise ValueError(
                f"No se permite el borrado físico de {tabla}; conserva el historial "
                "y registra una baja lógica cuando corresponda."
            )
    for registro in session.dirty:
        tabla = getattr(type(registro), "__tablename__", None)
        if tabla in _TABLAS_APPEND_ONLY and session.is_modified(
            registro,
            include_collections=True,
        ):
            raise ValueError("Los eventos de auditoría son inmutables.")


@event.listens_for(SQLAlchemySession, "do_orm_execute")
def impedir_borrado_masivo(execute_state: ORMExecuteState) -> None:
    tabla = getattr(execute_state.statement, "table", None)
    if tabla is None:
        return
    if tabla.name in _TABLAS_APPEND_ONLY and execute_state.is_update:
        raise ValueError("Los eventos de auditoría son inmutables.")
    if tabla.name in _TABLAS_APPEND_ONLY and execute_state.is_delete:
        raise ValueError("Los eventos de auditoría no se pueden borrar.")
    if tabla.name in _TABLAS_PROTEGIDAS_HISTORICAS and execute_state.is_delete:
        raise ValueError(
            f"No se permite el borrado físico de {tabla.name}; conserva el historial "
            "y registra una baja lógica cuando corresponda."
        )


def sembrar_catalogos_iniciales() -> None:
    """Asegurar los IDs institucionales del catálogo de condiciones."""
    from .models import CondicionMateria

    condiciones_iniciales = (
        (1, "APROBADO", "Aprobado"),
        (2, "DESAPROBADO", "Desaprobado"),
        (3, "LIBRE", "Libre"),
    )
    for id_condicion, codigo, nombre in condiciones_iniciales:
        condicion = db.session.get(CondicionMateria, id_condicion)
        if condicion is None:
            condicion = CondicionMateria()
            condicion.id = id_condicion
            condicion.codigo = codigo
            condicion.nombre = nombre
            db.session.add(condicion)
    db.session.commit()


def crear_respaldo_sqlite(engine: Engine, directorio: str | Path) -> Path | None:
    """Crear una copia consistente de una base SQLite persistente."""
    if engine.dialect.name != "sqlite":
        raise ValueError("El respaldo automático solo está implementado para SQLite.")

    ruta_base = engine.url.database
    if not ruta_base or ruta_base == ":memory:":
        return None

    origen = Path(ruta_base)
    if not origen.is_file():
        return None

    carpeta = Path(directorio)
    carpeta.mkdir(parents=True, exist_ok=True)
    marca_tiempo = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destino = carpeta / f"{origen.stem}-{marca_tiempo}.sqlite3"
    conexion_origen = engine.raw_connection()
    try:
        with closing(sqlite3.connect(destino)) as conexion_destino:
            conexion_origen.driver_connection.backup(conexion_destino)
            resultado = conexion_destino.execute("PRAGMA integrity_check").fetchone()
            if resultado is None or resultado[0] != "ok":
                raise RuntimeError("El respaldo SQLite no superó la comprobación de integridad.")
    except Exception:
        destino.unlink(missing_ok=True)
        raise
    finally:
        conexion_origen.close()

    return destino


def restaurar_respaldo_sqlite(respaldo: str | Path, destino: str | Path) -> None:
    """Restaurar una copia íntegra de SQLite con reemplazo atómico del archivo."""
    ruta_respaldo = Path(respaldo)
    ruta_destino = Path(destino)
    if not ruta_respaldo.is_file():
        raise FileNotFoundError(f"No existe el respaldo indicado: {ruta_respaldo}")
    if ruta_respaldo.resolve() == ruta_destino.resolve():
        raise ValueError("El respaldo y el destino deben ser archivos distintos.")

    ruta_destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta_destino.with_name(f".{ruta_destino.name}.{uuid4().hex}.restore.tmp")
    try:
        with closing(sqlite3.connect(ruta_respaldo)) as conexion_respaldo:
            resultado = conexion_respaldo.execute("PRAGMA integrity_check").fetchone()
            if resultado is None or resultado[0] != "ok":
                raise ValueError("El respaldo SQLite no superó la comprobación de integridad.")
            with closing(sqlite3.connect(temporal)) as conexion_destino:
                conexion_respaldo.backup(conexion_destino)
        temporal.replace(ruta_destino)
    except Exception:
        temporal.unlink(missing_ok=True)
        raise


def migrar_esquema(app: Flask) -> Path | None:
    """Aplicar las migraciones pendientes tras respaldar la base existente."""
    with app.app_context():
        extension = current_app.extensions["migrate"].migrate
        config = extension.get_config(app.config["MIGRATIONS_DIRECTORY"])
        script = ScriptDirectory.from_config(config)
        revisiones_objetivo = set(script.get_heads())
        if not revisiones_objetivo:
            raise RuntimeError(
                "No hay revisiones de esquema. Inicializá migrations y generá una "
                "revisión antes de iniciar la aplicación."
            )

        with db.engine.connect() as conexion:
            contexto = MigrationContext.configure(conexion)
            revisiones_actuales = set(contexto.get_current_heads())

        if revisiones_actuales == revisiones_objetivo:
            return None

        tablas_existentes = set(inspect(db.engine).get_table_names()) - {"alembic_version"}
        if not revisiones_actuales and tablas_existentes:
            respaldo = crear_respaldo_sqlite(db.engine, app.config["BACKUP_FOLDER"])
            app.config["LAST_MIGRATION_BACKUP"] = str(respaldo) if respaldo else None
            detalle_respaldo = f" El respaldo previo quedó en {respaldo}." if respaldo else ""
            raise RuntimeError(
                "La base contiene tablas sin versión de migración. No se aplicó ningún "
                "cambio. Verificá que el esquema coincida con la revisión inicial antes "
                f"de ejecutar `flask db stamp head`.{detalle_respaldo}"
            )

        app.config["LAST_MIGRATION_BACKUP"] = None
        try:
            upgrade(directory=app.config["MIGRATIONS_DIRECTORY"])
        except Exception as error:
            db.session.remove()
            respaldo = app.config.get("LAST_MIGRATION_BACKUP")
            detalle_respaldo = f" El respaldo previo quedó en {respaldo}." if respaldo else ""
            raise RuntimeError(
                f"No se pudo actualizar el esquema. No restaures mientras la aplicación "
                f"esté abierta.{detalle_respaldo}"
            ) from error
        respaldo = app.config.get("LAST_MIGRATION_BACKUP")
        return Path(respaldo) if respaldo else None
