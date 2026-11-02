import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from alembic import command
from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

from app import migrate
from app.database import (
    crear_respaldo_sqlite,
    db,
    migrar_esquema,
    restaurar_respaldo_sqlite,
)
from app.models import Alumno, CondicionMateria, Tutor


MIGRATIONS_DIRECTORY = Path(__file__).resolve().parents[1] / "migrations"


class RespaldoSQLiteTests(unittest.TestCase):
    def setUp(self):
        self.directorio = tempfile.TemporaryDirectory()
        self.ruta_base = Path(self.directorio.name) / "galileo.sqlite3"
        self.ruta_restaurada = Path(self.directorio.name) / "restaurada.sqlite3"
        engine = create_engine(URL.create("sqlite", database=str(self.ruta_base)))
        with engine.begin() as conexion:
            conexion.exec_driver_sql(
                "CREATE TABLE muestra (id INTEGER PRIMARY KEY, valor TEXT NOT NULL)"
            )
            conexion.exec_driver_sql(
                "INSERT INTO muestra (id, valor) VALUES (41, 'antes')"
            )
        self.engine = engine

    def tearDown(self):
        self.engine.dispose()
        self.directorio.cleanup()

    def test_respaldar_y_restaurar_preserva_registros_e_ids(self):
        respaldo = crear_respaldo_sqlite(
            self.engine,
            Path(self.directorio.name) / "respaldos",
        )
        self.assertIsNotNone(respaldo)
        if respaldo is None:
            self.fail("No se creó el respaldo esperado.")

        with self.engine.begin() as conexion:
            conexion.exec_driver_sql("UPDATE muestra SET valor = 'después' WHERE id = 41")
        self.engine.dispose()
        with closing(sqlite3.connect(self.ruta_restaurada)) as conexion:
            conexion.execute("CREATE TABLE obsoleta (id INTEGER PRIMARY KEY)")
            conexion.commit()

        restaurar_respaldo_sqlite(respaldo, self.ruta_restaurada)

        with closing(sqlite3.connect(self.ruta_restaurada)) as conexion:
            self.assertEqual(
                conexion.execute("SELECT id, valor FROM muestra").fetchall(),
                [(41, "antes")],
            )
            self.assertEqual(
                conexion.execute("PRAGMA integrity_check").fetchone(),
                ("ok",),
            )
            self.assertEqual(
                conexion.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'obsoleta'"
                ).fetchone(),
                None,
            )

    def test_respaldo_invalido_no_reemplaza_la_base_destino(self):
        archivo_invalido = Path(self.directorio.name) / "invalido.sqlite3"
        archivo_invalido.write_bytes(b"esto no es una base SQLite")
        with closing(sqlite3.connect(self.ruta_restaurada)) as conexion:
            conexion.execute("CREATE TABLE preservar (id INTEGER PRIMARY KEY)")
            conexion.execute("INSERT INTO preservar (id) VALUES (9)")
            conexion.commit()

        with self.assertRaises(sqlite3.DatabaseError):
            restaurar_respaldo_sqlite(archivo_invalido, self.ruta_restaurada)

        with closing(sqlite3.connect(self.ruta_restaurada)) as conexion:
            self.assertEqual(
                conexion.execute("SELECT id FROM preservar").fetchall(),
                [(9,)],
            )

    def test_respaldo_ignora_sqlite_en_memoria(self):
        engine_memoria = create_engine("sqlite://")
        try:
            self.assertIsNone(
                crear_respaldo_sqlite(engine_memoria, self.directorio.name)
            )
        finally:
            engine_memoria.dispose()


class MigracionDeEsquemaTests(unittest.TestCase):
    def setUp(self):
        self.directorio = tempfile.TemporaryDirectory()
        self.ruta_base = Path(self.directorio.name) / "galileo.sqlite3"
        self.app = Flask(__name__)
        self.app.config.update(
            SQLALCHEMY_DATABASE_URI=str(
                URL.create("sqlite", database=str(self.ruta_base))
            ),
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            BACKUP_FOLDER=str(Path(self.directorio.name) / "respaldos"),
            MIGRATIONS_DIRECTORY=str(MIGRATIONS_DIRECTORY),
        )
        db.init_app(self.app)
        migrate.init_app(
            self.app,
            db,
            directory=self.app.config["MIGRATIONS_DIRECTORY"],
        )

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.directorio.cleanup()

    def test_migra_esquema_y_reaplicar_no_altera_ids_ni_registros(self):
        with self.app.app_context():
            respaldo = migrar_esquema(self.app)
            self.assertIsNone(respaldo)
            condiciones = (
                db.session.query(CondicionMateria.id, CondicionMateria.codigo)
                .order_by(CondicionMateria.id)
                .all()
            )
            self.assertEqual(
                condiciones,
                [(1, "APROBADO"), (2, "DESAPROBADO"), (3, "LIBRE")],
            )

            tutor = Tutor(id=73, nombre="Responsable", dni_cuit="TEST-73")
            db.session.add(tutor)
            db.session.commit()

            self.assertIsNone(migrar_esquema(self.app))
            tutor_guardado = db.session.get(Tutor, 73)
            self.assertIsNotNone(tutor_guardado)
            self.assertEqual(tutor_guardado.dni_cuit, "TEST-73")

    def test_rechaza_base_sin_version_y_conserva_respaldo(self):
        with closing(sqlite3.connect(self.ruta_base)) as conexion:
            conexion.execute("CREATE TABLE legado (id INTEGER PRIMARY KEY, valor TEXT)")
            conexion.execute("INSERT INTO legado (id, valor) VALUES (8, 'conservar')")
            conexion.commit()

        with self.app.app_context():
            with self.assertRaisesRegex(RuntimeError, "sin versión de migración"):
                migrar_esquema(self.app)
            respaldo = Path(self.app.config["LAST_MIGRATION_BACKUP"])

        self.assertTrue(respaldo.is_file())
        with closing(sqlite3.connect(respaldo)) as conexion:
            self.assertEqual(
                conexion.execute("SELECT id, valor FROM legado").fetchall(),
                [(8, "conservar")],
            )
            self.assertEqual(
                conexion.execute("PRAGMA integrity_check").fetchone(),
                ("ok",),
            )

    def test_migracion_de_bajas_preserva_registros_existentes(self):
        with self.app.app_context():
            extension = self.app.extensions["migrate"].migrate
            config = extension.get_config(self.app.config["MIGRATIONS_DIRECTORY"])
            command.upgrade(config, "29e41a582da5")

            with db.engine.begin() as conexion:
                conexion.exec_driver_sql(
                    "INSERT INTO tutor (id, nombre, dni_cuit) VALUES (17, 'Tutor', 'T-17')"
                )
                conexion.exec_driver_sql(
                    "INSERT INTO alumno (id, id_tutor, nombre, apellido, dni) "
                    "VALUES (27, 17, 'Ana', 'Paz', 'A-27')"
                )

            respaldo = migrar_esquema(self.app)
            if respaldo is None:
                self.fail("La migración debía crear un respaldo de la base existente.")
            alumno = db.session.get(Alumno, 27)

            self.assertIsNotNone(alumno)
            self.assertEqual(alumno.dni, "A-27")
            self.assertIsNone(alumno.fecha_baja)
            self.assertIsNone(alumno.motivo_baja)
            self.assertTrue(respaldo.is_file())
