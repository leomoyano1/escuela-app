from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from flask import has_request_context
from flask_login import current_user
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from .audit import registrar_evento_auditoria
from .database import db
from .models import (
    Alumno,
    AnioLectivo,
    Asignatura,
    Asistencia,
    AspiranteCRM,
    CicloEscolar,
    CursoDireccion,
    DetalleFactura,
    Factura,
    GrupoSeccion,
    HistorialGrupoMatricula,
    InscripcionMateria,
    IntentoCalificacion,
    Matricula,
    NivelGrado,
    NotificacionAsistencia,
    Tutor,
    Usuario,
)


CENTAVO = Decimal("0.01")
TIPOS_EVALUACION = {
    "DIAGNOSTICO": "Diagnóstico",
    "PARCIAL_1": "1° Parcial",
    "PARCIAL_2": "2° Parcial",
    "EVALUACION_TRIMESTRAL": "Evaluación Trimestral",
    "RECUPERATORIO": "Recuperatorio",
    "NOTA_FINAL": "Nota Final",
}
UMBRAL_FALTAS_INJUSTIFICADAS = Decimal("15")


@dataclass(frozen=True)
class ConceptoFacturable:
    id_matricula: int
    concepto: str
    monto_base: Decimal
    recargo_mora: Decimal = Decimal("0.00")


@dataclass(frozen=True)
class DatosAspirante:
    nombre: str
    apellido: str
    dni: str
    fecha_nacimiento: date
    nombre_tutor: str
    dni_cuit_tutor: str
    telefono_whatsapp: str | None = None
    email_tutor: str | None = None
    direccion_tutor: str | None = None
    id_anio: int | None = None
    id_nivel: int | None = None
    legajo: str | None = None
    curso_interes: str | None = None
    estado_entrevista: str | None = None
    observaciones: str | None = None
    partida_nacimiento: int = 0
    documento: int = 0
    certificado_primaria: int = 0
    pase_otra_escuela: int = 0
    libre_deuda: int = 0
    plan_estudio: int = 0
    libro_matriz: int = 0
    materias_adeudadas: int = 0


def registrar_aspirante(datos: DatosAspirante) -> AspiranteCRM:
    """Guardar una ficha de aspirante en espera, sin crear aún un alumno."""
    nombre = _texto_requerido(datos.nombre, "nombre del alumno")
    apellido = _texto_requerido(datos.apellido, "apellido del alumno")
    dni = _texto_requerido(datos.dni, "DNI del alumno")
    nombre_tutor = _texto_requerido(datos.nombre_tutor, "nombre del tutor")
    dni_cuit_tutor = _texto_requerido(datos.dni_cuit_tutor, "DNI/CUIT del tutor")

    if datos.fecha_nacimiento > date.today():
        raise ValueError("La fecha de nacimiento no puede ser futura.")

    if datos.id_anio is not None and db.session.get(AnioLectivo, datos.id_anio) is None:
        raise ValueError("No existe el año lectivo indicado.")
    if datos.id_nivel is not None and db.session.get(NivelGrado, datos.id_nivel) is None:
        raise ValueError("No existe el nivel indicado.")

    flags = {
        "partida_nacimiento": _flag_documental(datos.partida_nacimiento, "partida de nacimiento"),
        "documento": _flag_documental(datos.documento, "documento"),
        "certificado_primaria": _flag_documental(
            datos.certificado_primaria,
            "certificado de primaria",
        ),
        "pase_otra_escuela": _flag_documental(datos.pase_otra_escuela, "pase de otra escuela"),
        "libre_deuda": _flag_documental(datos.libre_deuda, "libre deuda"),
        "plan_estudio": _flag_documental(datos.plan_estudio, "plan de estudio"),
        "libro_matriz": _flag_documental(datos.libro_matriz, "libro matriz"),
        "materias_adeudadas": _flag_documental(datos.materias_adeudadas, "materias adeudadas"),
    }

    aspirante = AspiranteCRM()
    aspirante.nombre = nombre
    aspirante.apellido = apellido
    aspirante.dni = dni
    aspirante.fecha_nacimiento = datos.fecha_nacimiento
    aspirante.nombre_tutor = nombre_tutor
    aspirante.dni_cuit_tutor = dni_cuit_tutor
    aspirante.telefono_whatsapp = _texto_opcional(datos.telefono_whatsapp)
    aspirante.email_tutor = _texto_opcional(datos.email_tutor)
    aspirante.direccion_tutor = _texto_opcional(datos.direccion_tutor)
    aspirante.id_anio = datos.id_anio
    aspirante.id_nivel = datos.id_nivel
    aspirante.legajo = _texto_opcional(datos.legajo)
    aspirante.curso_interes = _texto_opcional(datos.curso_interes)
    aspirante.estado_entrevista = _texto_opcional(datos.estado_entrevista)
    aspirante.estado = "En espera"
    aspirante.observaciones = _texto_opcional(datos.observaciones)
    for nombre_flag, valor in flags.items():
        setattr(aspirante, nombre_flag, valor)

    try:
        db.session.add(aspirante)
        db.session.flush()
        registrar_evento_auditoria(
            "aspirante.creado",
            "aspirante",
            aspirante.id,
            detalles={"resultado": "creado"},
        )
        db.session.commit()
        return aspirante
    except Exception:
        db.session.rollback()
        raise


def listar_aspirantes(estado: str = "En espera") -> list[AspiranteCRM]:
    """Obtener aspirantes por estado, ordenados del más antiguo al más reciente."""
    aspirantes = (
        db.session.query(AspiranteCRM)
        .filter_by(estado=estado)
        .filter(AspiranteCRM.fecha_baja.is_(None))
        .order_by(AspiranteCRM.fecha_registro, AspiranteCRM.id)
        .all()
    )
    registrar_evento_auditoria(
        "aspirantes.listados",
        "aspirante",
        resultado="correcto",
        detalles={"filtros": {"estado": estado}, "cantidad": len(aspirantes)},
    )
    db.session.commit()
    return aspirantes


def listar_aspirantes_archivados(estado: str | None = None) -> list[AspiranteCRM]:
    """Obtener aspirantes dados de baja, opcionalmente filtrados por estado."""
    consulta = db.session.query(AspiranteCRM).filter(AspiranteCRM.fecha_baja.is_not(None))
    if estado is not None:
        consulta = consulta.filter_by(estado=estado)
    aspirantes = consulta.order_by(AspiranteCRM.fecha_registro, AspiranteCRM.id).all()
    registrar_evento_auditoria(
        "aspirantes.archivados_listados",
        "aspirante",
        detalles={"filtros": {"estado": estado}, "cantidad": len(aspirantes)},
    )
    db.session.commit()
    return aspirantes


def listar_usuarios() -> list[Usuario]:
    usuarios = db.session.query(Usuario).order_by(Usuario.username).all()
    registrar_evento_auditoria(
        "cuentas.listadas",
        "usuario",
        detalles={"cantidad": len(usuarios)},
    )
    db.session.commit()
    return usuarios


def crear_nivel_grado(
    nombre_nivel: str,
    grado_año: str,
    actor_id: int | None = None,
) -> NivelGrado:
    actor_id = _actor_autenticado(actor_id)
    nivel = NivelGrado(
        nombre_nivel=_texto_requerido(nombre_nivel, "nivel"),
        grado_año=_texto_requerido(grado_año, "grado/año"),
    )
    return _guardar_catalogo(
        nivel,
        "nivel_grado.creado",
        "nivel_grado",
        {"nombre_nivel": nivel.nombre_nivel, "grado_año": nivel.grado_año},
        actor_id,
    )


def editar_nivel_grado(
    id_nivel: int,
    nombre_nivel: str,
    grado_año: str,
    actor_id: int | None = None,
) -> NivelGrado:
    actor_id = _actor_autenticado(actor_id)
    nivel = db.session.get(NivelGrado, _entero_positivo(id_nivel, "nivel"))
    if nivel is None:
        raise ValueError("No existe el nivel indicado.")
    nuevos = {
        "nombre_nivel": _texto_requerido(nombre_nivel, "nivel"),
        "grado_año": _texto_requerido(grado_año, "grado/año"),
    }
    return _editar_catalogo(
        nivel, "nivel_grado.editado", "nivel_grado", nuevos, actor_id
    )


def crear_asignatura(
    nombre_materia: str,
    carga_horaria: int,
    actor_id: int | None = None,
) -> Asignatura:
    actor_id = _actor_autenticado(actor_id)
    carga = _entero_no_negativo(carga_horaria, "carga horaria")
    asignatura = Asignatura(
        nombre_materia=_texto_requerido(nombre_materia, "asignatura"),
        carga_horaria=carga,
    )
    return _guardar_catalogo(
        asignatura,
        "asignatura.creada",
        "asignatura",
        {"nombre_materia": asignatura.nombre_materia, "carga_horaria": carga},
        actor_id,
    )


def editar_asignatura(
    id_asignatura: int,
    nombre_materia: str,
    carga_horaria: int,
    actor_id: int | None = None,
) -> Asignatura:
    actor_id = _actor_autenticado(actor_id)
    asignatura = db.session.get(
        Asignatura, _entero_positivo(id_asignatura, "asignatura")
    )
    if asignatura is None:
        raise ValueError("No existe la asignatura indicada.")
    nuevos = {
        "nombre_materia": _texto_requerido(nombre_materia, "asignatura"),
        "carga_horaria": _entero_no_negativo(carga_horaria, "carga horaria"),
    }
    return _editar_catalogo(
        asignatura, "asignatura.editada", "asignatura", nuevos, actor_id
    )


def crear_grupo_seccion(
    id_nivel: int,
    seccion: str | None,
    capacidad_maxima: int,
    actor_id: int | None = None,
) -> GrupoSeccion:
    actor_id = _actor_autenticado(actor_id)
    nivel_id = _entero_positivo(id_nivel, "nivel")
    if db.session.get(NivelGrado, nivel_id) is None:
        raise ValueError("No existe el nivel indicado.")
    grupo = GrupoSeccion(
        id_nivel=nivel_id,
        seccion=_texto_opcional(seccion),
        capacidad_maxima=_entero_positivo(capacidad_maxima, "capacidad máxima"),
    )
    return _guardar_catalogo(
        grupo,
        "grupo_seccion.creado",
        "grupo_seccion",
        {
            "id_nivel": grupo.id_nivel,
            "seccion": grupo.seccion,
            "capacidad_maxima": grupo.capacidad_maxima,
        },
        actor_id,
    )


def editar_grupo_seccion(
    id_grupo: int,
    id_nivel: int,
    seccion: str | None,
    capacidad_maxima: int,
    actor_id: int | None = None,
) -> GrupoSeccion:
    actor_id = _actor_autenticado(actor_id)
    grupo = db.session.get(GrupoSeccion, _entero_positivo(id_grupo, "grupo"))
    if grupo is None:
        raise ValueError("No existe el grupo indicado.")
    nivel_id = _entero_positivo(id_nivel, "nivel")
    if db.session.get(NivelGrado, nivel_id) is None:
        raise ValueError("No existe el nivel indicado.")
    nuevos = {
        "id_nivel": nivel_id,
        "seccion": _texto_opcional(seccion),
        "capacidad_maxima": _entero_positivo(capacidad_maxima, "capacidad máxima"),
    }
    if (
        (grupo.id_nivel != nuevos["id_nivel"] or grupo.seccion != nuevos["seccion"])
        and (
            db.session.query(HistorialGrupoMatricula.id)
            .filter_by(id_grupo=grupo.id)
            .first()
            or db.session.query(CursoDireccion.id)
            .filter_by(id_grupo=grupo.id)
            .first()
        )
    ):
        raise ValueError(
            "Un grupo usado por matrículas o asignaciones docentes no puede cambiar "
            "de nivel o sección; crea otro grupo y registra la transición."
        )
    return _editar_catalogo(
        grupo, "grupo_seccion.editado", "grupo_seccion", nuevos, actor_id
    )


def listar_niveles_grados(actor_id: int | None = None) -> list[NivelGrado]:
    actor_id = _actor_autenticado(actor_id)
    niveles = db.session.query(NivelGrado).order_by(NivelGrado.id).all()
    _auditar_listado(
        "niveles_grados.listados", "nivel_grado", len(niveles), actor_id
    )
    return niveles


def listar_asignaturas(actor_id: int | None = None) -> list[Asignatura]:
    actor_id = _actor_autenticado(actor_id)
    asignaturas = db.session.query(Asignatura).order_by(Asignatura.nombre_materia).all()
    _auditar_listado(
        "asignaturas.listadas", "asignatura", len(asignaturas), actor_id
    )
    return asignaturas


def listar_grupos_secciones(actor_id: int | None = None) -> list[GrupoSeccion]:
    actor_id = _actor_autenticado(actor_id)
    grupos = (
        db.session.query(GrupoSeccion)
        .order_by(GrupoSeccion.id_nivel, GrupoSeccion.seccion, GrupoSeccion.id)
        .all()
    )
    _auditar_listado(
        "grupos_secciones.listados", "grupo_seccion", len(grupos), actor_id
    )
    return grupos


def registrar_intento_calificacion(
    id_inscripcion_materia: int,
    trimestre: int,
    tipo_evaluacion: str,
    valor: int | str,
    actor_id: int | None = None,
) -> IntentoCalificacion:
    """Añadir un intento; nunca evalúa ni cambia la condición vigente."""
    actor_id = _actor_autenticado(actor_id)
    id_inscripcion_materia = _entero_positivo(
        id_inscripcion_materia,
        "inscripción por materia",
    )
    trimestre = _entero_positivo(trimestre, "trimestre")
    if trimestre > 3:
        raise ValueError("El trimestre debe ser 1, 2 o 3.")
    if tipo_evaluacion not in TIPOS_EVALUACION:
        raise ValueError("El tipo de evaluación no es válido.")
    if isinstance(valor, bool) or not isinstance(valor, (int, str)):
        raise ValueError("La nota debe ser un entero del 1 al 10 o A.")
    nota = str(valor).strip()
    if nota != "A" and not re.fullmatch(r"(?:[1-9]|10)", nota):
        raise ValueError("La nota debe ser un entero del 1 al 10 o A.")

    inscripcion = db.session.get(InscripcionMateria, id_inscripcion_materia)
    if inscripcion is None:
        raise ValueError("No existe la inscripción por materia indicada.")
    if inscripcion.id_condicion not in (None, 1, 2, 3):
        raise ValueError("La inscripción tiene una condición académica no reconocida.")

    registrado_en = datetime.now(timezone.utc)
    intento = IntentoCalificacion(
        id_inscripcion_materia=inscripcion.id,
        trimestre=trimestre,
        tipo_evaluacion=tipo_evaluacion,
        valor=nota,
        id_condicion_rendida=inscripcion.id_condicion,
        actor_id=actor_id,
        registrado_en=registrado_en,
    )
    try:
        db.session.add(intento)
        db.session.flush()
        registrar_evento_auditoria(
            "calificacion.intento_registrado",
            "intento_calificacion",
            intento.id,
            detalles={
                "cambios": {
                    "id_inscripcion_materia": {
                        "anterior": None,
                        "nuevo": inscripcion.id,
                    },
                    "trimestre": {"anterior": None, "nuevo": trimestre},
                    "tipo_evaluacion": {
                        "anterior": None,
                        "nuevo": tipo_evaluacion,
                    },
                    "valor": {"anterior": None, "nuevo": nota},
                    "id_condicion_rendida": {
                        "anterior": None,
                        "nuevo": inscripcion.id_condicion,
                    },
                    "actor_id": {"anterior": None, "nuevo": actor_id},
                    "registrado_en": {
                        "anterior": None,
                        "nuevo": registrado_en.isoformat(),
                    },
                }
            },
            actor_id=actor_id,
        )
        db.session.commit()
        return intento
    except IntegrityError as error:
        db.session.rollback()
        raise ValueError("No se pudo guardar el intento por una relación inválida.") from error
    except Exception:
        db.session.rollback()
        raise


def consultar_calificaciones(
    id_inscripcion_materia: int | None = None,
    trimestre: int | None = None,
    actor_id: int | None = None,
) -> tuple[list[InscripcionMateria], list[IntentoCalificacion]]:
    """Listar inscripciones e intentos sin registrar contenido de notas en la auditoría."""
    actor_id = _actor_autenticado(actor_id)
    if id_inscripcion_materia is not None:
        id_inscripcion_materia = _entero_positivo(
            id_inscripcion_materia,
            "inscripción por materia",
        )
        if db.session.get(InscripcionMateria, id_inscripcion_materia) is None:
            raise ValueError("No existe la inscripción por materia indicada.")
    if trimestre is not None:
        trimestre = _entero_positivo(trimestre, "trimestre")
        if trimestre > 3:
            raise ValueError("El trimestre debe ser 1, 2 o 3.")

    inscripciones = (
        db.session.query(InscripcionMateria)
        .join(InscripcionMateria.matricula)
        .join(Matricula.alumno)
        .join(InscripcionMateria.asignatura)
        .order_by(
            Matricula.id_anio.desc(),
            Alumno.apellido,
            Alumno.nombre,
            Asignatura.nombre_materia,
            InscripcionMateria.id,
        )
        .all()
    )
    consulta = db.session.query(IntentoCalificacion)
    if id_inscripcion_materia is not None:
        consulta = consulta.filter_by(
            id_inscripcion_materia=id_inscripcion_materia
        )
    if trimestre is not None:
        consulta = consulta.filter_by(trimestre=trimestre)
    intentos = consulta.order_by(
        IntentoCalificacion.registrado_en,
        IntentoCalificacion.id,
    ).all()

    registrar_evento_auditoria(
        "calificaciones.consultadas",
        "intento_calificacion",
        id_inscripcion_materia,
        detalles={
            "filtros": {
                "id_inscripcion_materia": id_inscripcion_materia,
                "trimestre": trimestre,
            },
            "resultados": {
                "inscripciones": len(inscripciones),
                "intentos": len(intentos),
            },
        },
        actor_id=actor_id,
    )
    db.session.commit()
    return inscripciones, intentos


def registrar_asistencia(
    id_matricula: int,
    fecha: date,
    valor_falta: int | float | Decimal,
    justificada: bool = False,
    observaciones: str | None = None,
    actor_id: int | None = None,
) -> Asistencia:
    """Crear o actualizar la asistencia diaria sin inferirla a partir de horarios."""
    actor_id = _actor_autenticado(actor_id)
    id_matricula = _entero_positivo(id_matricula, "matrícula")
    if not isinstance(fecha, date) or isinstance(fecha, datetime):
        raise ValueError("La fecha de asistencia debe ser válida.")
    if not isinstance(justificada, bool):
        raise ValueError("La justificación debe ser explícita.")
    try:
        valor = Decimal(str(valor_falta))
    except Exception as error:
        raise ValueError("El valor de falta debe ser 0, 0.5 o 1.") from error
    if not valor.is_finite() or valor not in (
        Decimal("0"),
        Decimal("0.5"),
        Decimal("1"),
    ):
        raise ValueError("El valor de falta debe ser 0, 0.5 o 1.")
    if justificada and valor == 0:
        raise ValueError("Solo se puede justificar una inasistencia.")
    if db.session.get(Matricula, id_matricula) is None:
        raise ValueError("No existe la matrícula indicada.")

    notas = _texto_opcional(observaciones)
    asistencia = (
        db.session.query(Asistencia)
        .filter_by(id_matricula=id_matricula, fecha=fecha)
        .one_or_none()
    )
    es_nueva = asistencia is None
    if es_nueva:
        asistencia = Asistencia(id_matricula=id_matricula, fecha=fecha)

    valores_nuevos: dict[str, object] = {
        "id_matricula": id_matricula,
        "fecha": fecha,
        "valor_falta": float(valor),
        "justificada": justificada,
        "observaciones": notas,
    }
    anteriores = {
        campo: getattr(asistencia, campo) if not es_nueva else None
        for campo in valores_nuevos
    }
    anteriores["justificada_por_id"] = (
        asistencia.justificada_por_id if not es_nueva else None
    )
    anteriores["justificada_en"] = asistencia.justificada_en if not es_nueva else None
    aporte_anterior = (
        Decimal(str(asistencia.valor_falta))
        if not es_nueva and not asistencia.justificada
        else Decimal("0")
    )
    for campo, nuevo in valores_nuevos.items():
        setattr(asistencia, campo, nuevo)

    justifico = justificada and (
        es_nueva
        or not bool(anteriores["justificada"])
        or anteriores["observaciones"] != notas
        or anteriores["valor_falta"] != float(valor)
    )
    ahora = datetime.now(timezone.utc)
    if justifico:
        asistencia.justificada_por_id = actor_id
        asistencia.justificada_en = ahora

    try:
        db.session.add(asistencia)
        db.session.flush()
        cambios = {
            campo: {
                "anterior": _valor_auditoria(anteriores[campo]),
                "nuevo": _valor_auditoria(nuevo),
            }
            for campo, nuevo in valores_nuevos.items()
            if anteriores[campo] != nuevo
        }
        if justifico:
            cambios["justificada_por_id"] = {
                "anterior": _valor_auditoria(anteriores.get("justificada_por_id")),
                "nuevo": actor_id,
            }
            cambios["justificada_en"] = {
                "anterior": _valor_auditoria(anteriores.get("justificada_en")),
                "nuevo": ahora.isoformat(),
            }
        if not cambios:
            db.session.rollback()
            raise ValueError("La asistencia no presenta cambios.")

        registrar_evento_auditoria(
            "asistencia.registrada" if es_nueva else "asistencia.editada",
            "asistencia",
            asistencia.id,
            detalles={"cambios": cambios},
            actor_id=actor_id,
        )
        aporte_nuevo = Decimal("0") if justificada else valor
        total_actual = _sumar_faltas_injustificadas(id_matricula)
        if aporte_nuevo > aporte_anterior and total_actual >= UMBRAL_FALTAS_INJUSTIFICADAS:
            notificacion = NotificacionAsistencia(
                id_asistencia=asistencia.id,
                faltas_injustificadas=total_actual,
                generado_en=ahora,
                actor_id=actor_id,
            )
            db.session.add(notificacion)
            db.session.flush()
            registrar_evento_auditoria(
                "asistencia.notificacion_generada",
                "notificacion_asistencia",
                notificacion.id,
                detalles={
                    "id_asistencia": asistencia.id,
                    "faltas_injustificadas": str(total_actual),
                },
                actor_id=actor_id,
            )
        db.session.commit()
        return asistencia
    except Exception:
        db.session.rollback()
        raise


def contar_faltas_injustificadas(
    id_matricula: int,
    actor_id: int | None = None,
) -> Decimal:
    """Sumar ausencias no justificadas en unidades de falta, incluidas medias."""
    id_matricula = _entero_positivo(id_matricula, "matrícula")
    total = _sumar_faltas_injustificadas(id_matricula)
    actor_id = _actor_autenticado(actor_id)
    registrar_evento_auditoria(
        "asistencia.contador_consultado",
        "matricula",
        id_matricula,
        detalles={"faltas_injustificadas": str(total)},
        actor_id=actor_id,
    )
    db.session.commit()
    return total


def _sumar_faltas_injustificadas(id_matricula: int) -> Decimal:
    id_matricula = _entero_positivo(id_matricula, "matrícula")
    valores = (
        db.session.query(Asistencia.valor_falta)
        .filter_by(id_matricula=id_matricula, justificada=False)
        .all()
    )
    return sum((Decimal(str(fila[0])) for fila in valores), Decimal("0"))


def consultar_asistencias(
    id_matricula: int | None = None,
    actor_id: int | None = None,
) -> tuple[
    list[Matricula],
    list[Asistencia],
    list[NotificacionAsistencia],
    dict[int, Decimal],
]:
    """Consultar asistencias y avisos, registrando solo filtros e identificadores."""
    actor_id = _actor_autenticado(actor_id)
    if id_matricula is not None:
        id_matricula = _entero_positivo(id_matricula, "matrícula")
        if db.session.get(Matricula, id_matricula) is None:
            raise ValueError("No existe la matrícula indicada.")

    matriculas = (
        db.session.query(Matricula)
        .join(Matricula.alumno)
        .order_by(
            Matricula.id_anio.desc(),
            Alumno.apellido,
            Alumno.nombre,
            Matricula.id,
        )
        .all()
    )
    asistencias_consulta = db.session.query(Asistencia)
    notificaciones_consulta = db.session.query(NotificacionAsistencia)
    if id_matricula is not None:
        asistencias_consulta = asistencias_consulta.filter_by(
            id_matricula=id_matricula
        )
        notificaciones_consulta = notificaciones_consulta.join(
            NotificacionAsistencia.asistencia
        ).filter(Asistencia.id_matricula == id_matricula)
    asistencias = asistencias_consulta.order_by(
        Asistencia.fecha.desc(),
        Asistencia.id.desc(),
    ).limit(100).all()
    notificaciones = notificaciones_consulta.order_by(
        NotificacionAsistencia.generado_en.desc(),
        NotificacionAsistencia.id.desc(),
    ).limit(50).all()
    contadores = {
        matricula_id: Decimal(str(total))
        for matricula_id, total in (
            db.session.query(
                Asistencia.id_matricula,
                func.sum(Asistencia.valor_falta),
            )
            .filter(Asistencia.justificada.is_(False))
            .group_by(Asistencia.id_matricula)
            .all()
        )
    }
    for matricula in matriculas:
        contadores.setdefault(matricula.id, Decimal("0"))
    registrar_evento_auditoria(
        "asistencias.consultadas",
        "asistencia",
        detalles={
            "filtros": {"id_matricula": id_matricula},
            "resultados": {
                "matriculas": len(matriculas),
                "asistencias": len(asistencias),
                "notificaciones": len(notificaciones),
            },
        },
        actor_id=actor_id,
    )
    db.session.commit()
    return matriculas, asistencias, notificaciones, contadores


def cambiar_grupo_matricula(
    id_matricula: int,
    id_grupo: int,
    fecha_efectiva: date,
    actor_id: int | None = None,
) -> HistorialGrupoMatricula:
    """Cambiar de división sin crear otra matrícula anual."""
    actor_id = _actor_autenticado(actor_id)
    matricula_id = _entero_positivo(id_matricula, "matrícula")
    grupo_id = _entero_positivo(id_grupo, "grupo")
    efectiva = _fecha_estricta(fecha_efectiva, "fecha efectiva")
    matricula = db.session.get(Matricula, matricula_id)
    if matricula is None:
        raise ValueError("No existe la matrícula indicada.")
    nuevo_grupo = db.session.get(GrupoSeccion, grupo_id)
    if nuevo_grupo is None:
        raise ValueError("No existe el grupo indicado.")
    actualizaciones = (
        db.session.query(HistorialGrupoMatricula)
        .filter_by(id_matricula=matricula_id, fecha_hasta=None)
        .all()
    )
    if len(actualizaciones) != 1:
        raise ValueError("La matrícula no tiene exactamente una asignación de grupo activa.")
    vigente = actualizaciones[0]
    if vigente.id_grupo != matricula.id_grupo:
        raise ValueError("El historial activo no coincide con el grupo vigente de la matrícula.")
    if nuevo_grupo.id_nivel != vigente.grupo.id_nivel:
        raise ValueError("El cambio de división debe conservar el nivel/grado de la matrícula.")
    if nuevo_grupo.id == vigente.id_grupo:
        raise ValueError("La matrícula ya pertenece a ese grupo.")
    if efectiva <= vigente.fecha_desde:
        raise ValueError("La fecha efectiva debe ser posterior al inicio del período vigente.")
    if efectiva < matricula.anio_lectivo.fecha_inicio or efectiva > matricula.anio_lectivo.fecha_fin:
        raise ValueError("La fecha efectiva debe estar dentro del año lectivo de la matrícula.")

    fecha_cierre = date.fromordinal(efectiva.toordinal() - 1)
    anterior_grupo = matricula.id_grupo
    nuevo_periodo = HistorialGrupoMatricula(
        matricula=matricula,
        grupo=nuevo_grupo,
        fecha_desde=efectiva,
    )
    try:
        vigente.fecha_hasta = fecha_cierre
        matricula.id_grupo = nuevo_grupo.id
        db.session.add(nuevo_periodo)
        db.session.flush()
        registrar_evento_auditoria(
            "matricula.grupo_cambiado",
            "matricula",
            matricula.id,
            detalles={
                "cambios": {
                    "id_grupo": {"anterior": anterior_grupo, "nuevo": nuevo_grupo.id},
                },
                "historial": {
                    "periodo_cerrado_id": vigente.id,
                    "periodo_nuevo_id": nuevo_periodo.id,
                },
            },
            actor_id=actor_id,
        )
        registrar_evento_auditoria(
            "historial_grupo_matricula.cerrado",
            "historial_grupo_matricula",
            vigente.id,
            detalles={
                "id_matricula": matricula.id,
                "cambios": {
                    "fecha_hasta": {
                        "anterior": None,
                        "nuevo": fecha_cierre.isoformat(),
                    }
                },
            },
            actor_id=actor_id,
        )
        registrar_evento_auditoria(
            "historial_grupo_matricula.creado",
            "historial_grupo_matricula",
            nuevo_periodo.id,
            detalles={
                "id_matricula": matricula.id,
                "cambios": {
                    "id_grupo": {"anterior": None, "nuevo": nuevo_grupo.id},
                    "fecha_desde": {"anterior": None, "nuevo": efectiva.isoformat()},
                    "fecha_hasta": {"anterior": None, "nuevo": None},
                },
            },
            actor_id=actor_id,
        )
        db.session.commit()
        return nuevo_periodo
    except Exception:
        db.session.rollback()
        raise


def listar_historial_grupo_matricula(
    id_matricula: int,
    actor_id: int | None = None,
) -> list[HistorialGrupoMatricula]:
    actor_id = _actor_autenticado(actor_id)
    matricula_id = _entero_positivo(id_matricula, "matrícula")
    if db.session.get(Matricula, matricula_id) is None:
        raise ValueError("No existe la matrícula indicada.")
    historial = (
        db.session.query(HistorialGrupoMatricula)
        .filter_by(id_matricula=matricula_id)
        .order_by(HistorialGrupoMatricula.fecha_desde, HistorialGrupoMatricula.id)
        .all()
    )
    registrar_evento_auditoria(
        "matricula.historial_grupos_consultado",
        "matricula",
        matricula_id,
        detalles={"cantidad": len(historial)},
        actor_id=actor_id,
    )
    db.session.commit()
    return historial


def _guardar_catalogo(
    entidad: object,
    accion: str,
    nombre_entidad: str,
    valores: dict[str, object],
    actor_id: int | None,
):
    try:
        db.session.add(entidad)
        db.session.flush()
        registrar_evento_auditoria(
            accion,
            nombre_entidad,
            entidad.id,
            detalles={
                "cambios": {
                    campo: {"anterior": None, "nuevo": _valor_auditoria(valor)}
                    for campo, valor in valores.items()
                }
            },
            actor_id=actor_id,
        )
        db.session.commit()
        return entidad
    except IntegrityError as error:
        db.session.rollback()
        raise ValueError("Los datos ingresados entran en conflicto con el catálogo.") from error
    except Exception:
        db.session.rollback()
        raise


def _editar_catalogo(
    entidad: object,
    accion: str,
    nombre_entidad: str,
    nuevos: dict[str, object],
    actor_id: int | None,
):
    cambios = {
        campo: {
            "anterior": _valor_auditoria(getattr(entidad, campo)),
            "nuevo": _valor_auditoria(valor),
        }
        for campo, valor in nuevos.items()
        if getattr(entidad, campo) != valor
    }
    try:
        for campo, valor in nuevos.items():
            setattr(entidad, campo, valor)
        db.session.flush()
        if cambios:
            registrar_evento_auditoria(
                accion,
                nombre_entidad,
                entidad.id,
                detalles={"cambios": cambios},
                actor_id=actor_id,
            )
        db.session.commit()
        return entidad
    except IntegrityError as error:
        db.session.rollback()
        raise ValueError("Los datos ingresados entran en conflicto con el catálogo.") from error
    except Exception:
        db.session.rollback()
        raise


def _auditar_listado(
    accion: str,
    entidad: str,
    cantidad: int,
    actor_id: int,
) -> None:
    registrar_evento_auditoria(
        accion,
        entidad,
        detalles={"cantidad": cantidad},
        actor_id=actor_id,
    )
    db.session.commit()


def _valor_auditoria(valor: object) -> object:
    return valor.isoformat() if isinstance(valor, (date, datetime)) else valor


def _entero_no_negativo(valor: int, nombre: str) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int) or valor < 0:
        raise ValueError(f"El campo {nombre} debe ser un entero no negativo.")
    return valor


def _actor_autenticado(actor_id: int | None) -> int:
    if actor_id is None and has_request_context() and current_user.is_authenticated:
        actor_id = int(current_user.get_id())
    if actor_id is None:
        raise ValueError("La operación requiere un usuario autenticado.")
    usuario = db.session.get(Usuario, _entero_positivo(actor_id, "usuario"))
    if usuario is None or not usuario.activo:
        raise ValueError("El usuario autenticado no existe o está inactivo.")
    return usuario.id


def crear_anio_lectivo(
    numero_ciclo: int,
    fecha_inicio: date,
    fecha_fin: date,
    actor_id: int | None = None,
) -> AnioLectivo:
    """Crear un año lectivo con fechas institucionales explícitas."""
    numero = _entero_positivo(numero_ciclo, "número de ciclo")
    inicio = _fecha_estricta(fecha_inicio, "fecha de inicio")
    fin = _fecha_estricta(fecha_fin, "fecha de fin")
    if fin < inicio:
        raise ValueError("La fecha de fin no puede ser anterior a la de inicio.")
    if db.session.query(AnioLectivo.id).filter_by(numero_ciclo=numero).first():
        raise ValueError("Ese número de ciclo ya está registrado.")

    anio = AnioLectivo(
        numero_ciclo=numero,
        fecha_inicio=inicio,
        fecha_fin=fin,
    )
    try:
        db.session.add(anio)
        db.session.flush()
        registrar_evento_auditoria(
            "anio_lectivo.creado",
            "anio_lectivo",
            anio.id,
            detalles={
                "cambios": {
                    "numero_ciclo": {"anterior": None, "nuevo": numero},
                    "fecha_inicio": {"anterior": None, "nuevo": inicio.isoformat()},
                    "fecha_fin": {"anterior": None, "nuevo": fin.isoformat()},
                }
            },
            actor_id=actor_id,
        )
        db.session.commit()
        return anio
    except IntegrityError as error:
        db.session.rollback()
        raise ValueError("No se pudo guardar el año lectivo por una restricción de datos.") from error
    except Exception:
        db.session.rollback()
        raise


def listar_anios_lectivos() -> list[AnioLectivo]:
    anios = (
        db.session.query(AnioLectivo)
        .order_by(AnioLectivo.numero_ciclo, AnioLectivo.id)
        .all()
    )
    registrar_evento_auditoria(
        "anios_lectivos.listados",
        "anio_lectivo",
        detalles={"cantidad": len(anios)},
    )
    db.session.commit()
    return anios


def editar_anio_lectivo(
    id_anio: int,
    numero_ciclo: int,
    fecha_inicio: date,
    fecha_fin: date,
    actor_id: int | None = None,
) -> AnioLectivo:
    """Editar identificador institucional y rango de fechas del año."""
    anio_id = _entero_positivo(id_anio, "año lectivo")
    numero = _entero_positivo(numero_ciclo, "número de ciclo")
    inicio = _fecha_estricta(fecha_inicio, "fecha de inicio")
    fin = _fecha_estricta(fecha_fin, "fecha de fin")
    if fin < inicio:
        raise ValueError("La fecha de fin no puede ser anterior a la de inicio.")

    anio = db.session.get(AnioLectivo, anio_id)
    if anio is None:
        raise ValueError("No existe el año lectivo indicado.")
    duplicado = (
        db.session.query(AnioLectivo.id)
        .filter(AnioLectivo.numero_ciclo == numero, AnioLectivo.id != anio_id)
        .first()
    )
    if duplicado:
        raise ValueError("Ese número de ciclo ya está registrado.")
    _validar_ciclos_en_rango(anio_id, inicio, fin)

    nuevos_valores = {
        "numero_ciclo": numero,
        "fecha_inicio": inicio,
        "fecha_fin": fin,
    }
    cambios = _cambios_auditables(anio, nuevos_valores)
    try:
        for campo, valor in nuevos_valores.items():
            setattr(anio, campo, valor)
        db.session.flush()
        registrar_evento_auditoria(
            "anio_lectivo.editado",
            "anio_lectivo",
            anio.id,
            detalles={"cambios": cambios},
            actor_id=actor_id,
        )
        db.session.commit()
        return anio
    except IntegrityError as error:
        db.session.rollback()
        raise ValueError("No se pudo guardar el año lectivo por una restricción de datos.") from error
    except Exception:
        db.session.rollback()
        raise


def crear_ciclo_escolar(
    id_anio: int,
    id_nivel: int | None,
    fecha_apertura: date,
    fecha_cierre: date,
    actor_id: int | None = None,
) -> CicloEscolar:
    """Crear un ciclo regular y validar su vínculo y rango institucional."""
    anio_id = _entero_positivo(id_anio, "año lectivo")
    nivel_id = _id_opcional(id_nivel, "nivel")
    apertura = _fecha_estricta(fecha_apertura, "fecha de apertura")
    cierre = _fecha_estricta(fecha_cierre, "fecha de cierre")
    anio = db.session.get(AnioLectivo, anio_id)
    if anio is None:
        raise ValueError("No existe el año lectivo indicado.")
    _validar_rango_ciclo(anio, apertura, cierre)
    _validar_nivel(nivel_id)
    _validar_unicidad_ciclo(anio_id, nivel_id)

    ciclo = CicloEscolar(
        id_anio=anio_id,
        id_nivel=nivel_id,
        fecha_apertura=apertura,
        fecha_cierre=cierre,
    )
    try:
        db.session.add(ciclo)
        db.session.flush()
        registrar_evento_auditoria(
            "ciclo_escolar.creado",
            "ciclo_escolar",
            ciclo.id,
            detalles={
                "cambios": {
                    "id_anio": {"anterior": None, "nuevo": anio_id},
                    "id_nivel": {"anterior": None, "nuevo": nivel_id},
                    "fecha_apertura": {"anterior": None, "nuevo": apertura.isoformat()},
                    "fecha_cierre": {"anterior": None, "nuevo": cierre.isoformat()},
                }
            },
            actor_id=actor_id,
        )
        db.session.commit()
        return ciclo
    except IntegrityError as error:
        db.session.rollback()
        raise ValueError("No se pudo guardar el ciclo por una restricción de datos.") from error
    except Exception:
        db.session.rollback()
        raise


def listar_ciclos_escolares() -> list[CicloEscolar]:
    ciclos = (
        db.session.query(CicloEscolar)
        .order_by(CicloEscolar.id_anio, CicloEscolar.id_nivel, CicloEscolar.id)
        .all()
    )
    registrar_evento_auditoria(
        "ciclos_escolares.listados",
        "ciclo_escolar",
        detalles={"cantidad": len(ciclos)},
    )
    db.session.commit()
    return ciclos


def editar_ciclo_escolar(
    id_ciclo: int,
    id_anio: int,
    id_nivel: int | None,
    fecha_apertura: date,
    fecha_cierre: date,
    actor_id: int | None = None,
) -> CicloEscolar:
    """Editar período o asociación de un ciclo con año/nivel existentes."""
    ciclo_id = _entero_positivo(id_ciclo, "ciclo escolar")
    anio_id = _entero_positivo(id_anio, "año lectivo")
    nivel_id = _id_opcional(id_nivel, "nivel")
    apertura = _fecha_estricta(fecha_apertura, "fecha de apertura")
    cierre = _fecha_estricta(fecha_cierre, "fecha de cierre")
    ciclo = db.session.get(CicloEscolar, ciclo_id)
    if ciclo is None:
        raise ValueError("No existe el ciclo escolar indicado.")
    anio = db.session.get(AnioLectivo, anio_id)
    if anio is None:
        raise ValueError("No existe el año lectivo indicado.")
    _validar_rango_ciclo(anio, apertura, cierre)
    _validar_nivel(nivel_id)
    _validar_unicidad_ciclo(anio_id, nivel_id, excluir_id=ciclo_id)

    nuevos_valores = {
        "id_anio": anio_id,
        "id_nivel": nivel_id,
        "fecha_apertura": apertura,
        "fecha_cierre": cierre,
    }
    cambios = _cambios_auditables(ciclo, nuevos_valores)
    try:
        for campo, valor in nuevos_valores.items():
            setattr(ciclo, campo, valor)
        db.session.flush()
        registrar_evento_auditoria(
            "ciclo_escolar.editado",
            "ciclo_escolar",
            ciclo.id,
            detalles={"cambios": cambios},
            actor_id=actor_id,
        )
        db.session.commit()
        return ciclo
    except IntegrityError as error:
        db.session.rollback()
        raise ValueError("No se pudo guardar el ciclo por una restricción de datos.") from error
    except Exception:
        db.session.rollback()
        raise


def _entero_positivo(valor: int, nombre: str) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
        raise ValueError(f"El {nombre} debe ser un entero positivo.")
    return valor


def _id_opcional(valor: int | None, nombre: str) -> int | None:
    if valor is None:
        return None
    return _entero_positivo(valor, nombre)


def _fecha_estricta(valor: date, nombre: str) -> date:
    if isinstance(valor, datetime) or not isinstance(valor, date):
        raise ValueError(f"El {nombre} debe ser una fecha válida.")
    return valor


def _validar_nivel(id_nivel: int | None) -> None:
    if id_nivel is not None and db.session.get(NivelGrado, id_nivel) is None:
        raise ValueError("No existe el nivel indicado.")


def _validar_rango_ciclo(anio: AnioLectivo, apertura: date, cierre: date) -> None:
    if cierre < apertura:
        raise ValueError("La fecha de cierre no puede ser anterior a la de apertura.")
    if apertura < anio.fecha_inicio or cierre > anio.fecha_fin:
        raise ValueError("El ciclo debe quedar comprendido en las fechas del año lectivo.")


def _validar_ciclos_en_rango(id_anio: int, inicio: date, fin: date) -> None:
    ciclo_fuera_de_rango = (
        db.session.query(CicloEscolar.id)
        .filter(
            CicloEscolar.id_anio == id_anio,
            (
                (CicloEscolar.fecha_apertura < inicio)
                | (CicloEscolar.fecha_cierre > fin)
            ),
        )
        .first()
    )
    if ciclo_fuera_de_rango:
        raise ValueError("Las nuevas fechas dejarían un ciclo escolar fuera del año lectivo.")


def _validar_unicidad_ciclo(
    id_anio: int,
    id_nivel: int | None,
    excluir_id: int | None = None,
) -> None:
    consulta = db.session.query(CicloEscolar.id).filter(
        CicloEscolar.id_anio == id_anio,
        CicloEscolar.id_nivel == id_nivel,
    )
    if excluir_id is not None:
        consulta = consulta.filter(CicloEscolar.id != excluir_id)
    if consulta.first():
        if id_nivel is None:
            raise ValueError("Ya existe un ciclo global para ese año lectivo.")
        raise ValueError("Ya existe un ciclo para ese nivel y año lectivo.")


def _cambios_auditables(registro: object, valores: dict[str, object]) -> dict[str, object]:
    cambios = {}
    for campo, nuevo in valores.items():
        anterior = getattr(registro, campo)
        if isinstance(anterior, date):
            anterior = anterior.isoformat()
        if isinstance(nuevo, date):
            nuevo = nuevo.isoformat()
        if anterior != nuevo:
            cambios[campo] = {"anterior": anterior, "nuevo": nuevo}
    return cambios


def listar_alumnos_mantenimiento(
    actor_id: int | None = None,
) -> list[Alumno]:
    """Listar alumnos activos para acceso administrativo, sin registrar sus datos."""
    actor_id = _actor_autenticado(actor_id)
    alumnos = (
        db.session.query(Alumno)
        .filter(Alumno.fecha_baja.is_(None))
        .order_by(Alumno.apellido, Alumno.nombre, Alumno.id)
        .all()
    )
    registrar_evento_auditoria(
        "alumnos.listados",
        "alumno",
        detalles={"filtros": {"baja": "sin_baja"}, "ids": [alumno.id for alumno in alumnos]},
        actor_id=actor_id,
    )
    db.session.commit()
    return alumnos


def listar_tutores_mantenimiento(
    actor_id: int | None = None,
) -> list[Tutor]:
    """Listar responsables existentes sin incluir sus datos en la bitácora."""
    actor_id = _actor_autenticado(actor_id)
    tutores = db.session.query(Tutor).order_by(Tutor.nombre, Tutor.id).all()
    registrar_evento_auditoria(
        "tutores.listados",
        "tutor",
        detalles={"ids": [tutor.id for tutor in tutores]},
        actor_id=actor_id,
    )
    db.session.commit()
    return tutores


def obtener_alumno_mantenimiento(
    id_alumno: int,
    actor_id: int | None = None,
) -> Alumno:
    actor_id = _actor_autenticado(actor_id)
    alumno_id = _entero_positivo(id_alumno, "alumno")
    alumno = db.session.get(Alumno, alumno_id)
    if alumno is None:
        raise ValueError("No existe el alumno indicado.")
    registrar_evento_auditoria(
        "alumno.ficha_consultada",
        "alumno",
        alumno.id,
        detalles={"resultado": "cargado"},
        actor_id=actor_id,
    )
    db.session.commit()
    return alumno


def obtener_tutor_mantenimiento(
    id_tutor: int,
    actor_id: int | None = None,
) -> Tutor:
    actor_id = _actor_autenticado(actor_id)
    tutor_id = _entero_positivo(id_tutor, "tutor")
    tutor = db.session.get(Tutor, tutor_id)
    if tutor is None:
        raise ValueError("No existe el tutor indicado.")
    registrar_evento_auditoria(
        "tutor.ficha_consultada",
        "tutor",
        tutor.id,
        detalles={"resultado": "cargado"},
        actor_id=actor_id,
    )
    db.session.commit()
    return tutor


def editar_alumno_existente(
    id_alumno: int,
    nombre: str,
    apellido: str,
    dni: str,
    fecha_nacimiento: date,
    actor_id: int | None = None,
) -> Alumno:
    """Actualizar datos personales sin alterar el legajo ni su historia."""
    actor_id = _actor_autenticado(actor_id)
    alumno_id = _entero_positivo(id_alumno, "alumno")
    nombre_validado = _texto_requerido(nombre, "nombre del alumno")
    apellido_validado = _texto_requerido(apellido, "apellido del alumno")
    dni_validado = _texto_requerido(dni, "DNI del alumno")
    nacimiento = _fecha_estricta(fecha_nacimiento, "fecha de nacimiento")
    if nacimiento > date.today():
        raise ValueError("La fecha de nacimiento no puede ser futura.")

    alumno = db.session.get(Alumno, alumno_id)
    if alumno is None:
        raise ValueError("No existe el alumno indicado.")
    duplicado = db.session.query(Alumno.id).filter(
        Alumno.dni == dni_validado,
        Alumno.id != alumno_id,
    ).first()
    if duplicado:
        raise ValueError("Ese DNI ya está registrado para otro alumno.")

    valores = {
        "nombre": nombre_validado,
        "apellido": apellido_validado,
        "dni": dni_validado,
        "fecha_nacimiento": nacimiento,
    }
    return _guardar_cambios_personales(
        alumno,
        valores,
        "alumno.editado",
        "alumno",
        actor_id,
    )


def editar_tutor_existente(
    id_tutor: int,
    nombre: str,
    dni_cuit: str,
    telefono: str,
    direccion: str,
    email: str | None = None,
    actor_id: int | None = None,
) -> Tutor:
    """Actualizar datos del responsable existente sin alterar cargos históricos."""
    actor_id = _actor_autenticado(actor_id)
    tutor_id = _entero_positivo(id_tutor, "tutor")
    tutor = db.session.get(Tutor, tutor_id)
    if tutor is None:
        raise ValueError("No existe el tutor indicado.")

    nombre_validado = _texto_requerido(nombre, "nombre del tutor")
    dni_validado = _texto_requerido(dni_cuit, "DNI/CUIT del tutor")
    telefono_validado = _texto_requerido(telefono, "teléfono/WhatsApp")
    direccion_validada = _texto_requerido(direccion, "domicilio del tutor")
    email_validado = _texto_opcional(email)
    duplicado = db.session.query(Tutor.id).filter(
        Tutor.dni_cuit == dni_validado,
        Tutor.id != tutor_id,
    ).first()
    if duplicado:
        raise ValueError("Ese DNI/CUIT ya está registrado para otro tutor.")

    valores = {
        "nombre": nombre_validado,
        "dni_cuit": dni_validado,
        "telefono": telefono_validado,
        "direccion": direccion_validada,
        "email": email_validado,
    }
    return _guardar_cambios_personales(
        tutor,
        valores,
        "tutor.editado",
        "tutor",
        actor_id,
    )


def _guardar_cambios_personales(
    registro: Alumno | Tutor,
    valores: dict[str, object],
    accion: str,
    entidad: str,
    actor_id: int,
) -> Alumno | Tutor:
    cambios = _cambios_auditables(registro, valores)
    try:
        for campo, valor in valores.items():
            setattr(registro, campo, valor)
        db.session.flush()
        if cambios:
            registrar_evento_auditoria(
                accion,
                entidad,
                registro.id,
                detalles={"cambios": cambios},
                actor_id=actor_id,
            )
        db.session.commit()
        return registro
    except IntegrityError as error:
        db.session.rollback()
        raise ValueError(
            "Los datos ingresados entran en conflicto con otro registro."
        ) from error
    except Exception:
        db.session.rollback()
        raise


def crear_usuario(
    username: str,
    password: str,
    bootstrap: bool = False,
    actor_id: int | None = None,
) -> Usuario:
    """Crear una cuenta local; el alta inicial solo está permitida sin cuentas."""
    nombre_usuario = _normalizar_username(username)
    if len(password) < 12:
        raise ValueError("La contraseña debe tener al menos 12 caracteres.")
    if db.session.query(Usuario.id).filter_by(username=nombre_usuario).first():
        raise ValueError("Ese nombre de usuario ya existe.")

    cantidad_cuentas = db.session.query(func.count(Usuario.id)).scalar() or 0
    if bootstrap and cantidad_cuentas:
        raise ValueError("La configuración inicial ya fue completada.")
    if not bootstrap and cantidad_cuentas == 0:
        raise ValueError("Primero debe crearse la cuenta inicial.")
    if actor_id is None and has_request_context() and current_user.is_authenticated:
        actor_id = int(current_user.get_id())
    if not bootstrap and actor_id is None:
        raise ValueError("Se requiere una cuenta autenticada para crear usuarios.")

    usuario = Usuario(username=nombre_usuario)
    usuario.set_password(password)
    try:
        db.session.add(usuario)
        db.session.flush()
        registrar_evento_auditoria(
            "cuenta.creada",
            "usuario",
            usuario.id,
            detalles={"username": nombre_usuario},
            actor_id=usuario.id if bootstrap else actor_id,
        )
        db.session.commit()
        return usuario
    except Exception:
        db.session.rollback()
        raise


def _normalizar_username(username: str) -> str:
    nombre_usuario = _texto_requerido(username, "nombre de usuario").lower()
    if not re.fullmatch(r"[a-z0-9._-]{3,64}", nombre_usuario):
        raise ValueError(
            "El nombre de usuario debe tener entre 3 y 64 caracteres: "
            "letras sin acentos, números, punto, guion o guion bajo."
        )
    return nombre_usuario


def dar_de_baja_alumno(
    id_alumno: int,
    motivo: str,
    fecha_baja: date | None = None,
) -> Alumno:
    """Archivar un alumno sin eliminar sus matrículas ni su historial."""
    alumno = db.session.get(Alumno, id_alumno)
    if alumno is None:
        raise ValueError("No existe el alumno indicado.")
    _registrar_baja(alumno, "alumno", motivo, fecha_baja)
    return alumno


def dar_de_baja_matricula(
    id_matricula: int,
    motivo: str,
    fecha_baja: date | None = None,
) -> Matricula:
    """Archivar una matrícula sin modificar su estado ni sus registros asociados."""
    matricula = db.session.get(Matricula, id_matricula)
    if matricula is None:
        raise ValueError("No existe la matrícula indicada.")
    _registrar_baja(matricula, "matrícula", motivo, fecha_baja)
    return matricula


def dar_de_baja_aspirante(
    id_aspirante: int,
    motivo: str,
    fecha_baja: date | None = None,
) -> AspiranteCRM:
    """Archivar un aspirante sin eliminar su ficha ni cambiar su etapa."""
    aspirante = db.session.get(AspiranteCRM, id_aspirante)
    if aspirante is None:
        raise ValueError("No existe el aspirante indicado.")
    _registrar_baja(aspirante, "aspirante", motivo, fecha_baja)
    return aspirante


def _registrar_baja(
    registro: Alumno | Matricula | AspiranteCRM,
    nombre_entidad: str,
    motivo: str,
    fecha_baja: date | None,
) -> None:
    motivo_validado = _texto_requerido(motivo, "motivo de baja")
    if registro.fecha_baja is not None:
        raise ValueError(f"El registro de {nombre_entidad} ya tiene una baja registrada.")

    registro.fecha_baja = fecha_baja or date.today()
    registro.motivo_baja = motivo_validado
    try:
        db.session.flush()
        registrar_evento_auditoria(
            f"{nombre_entidad}.dado_de_baja",
            nombre_entidad,
            registro.id,
            detalles={
                "cambios": {
                    "fecha_baja": {"anterior": None, "nuevo": registro.fecha_baja.isoformat()},
                    "motivo_baja": {"anterior": None, "nuevo": motivo_validado},
                }
            },
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def _texto_requerido(valor: str, nombre: str) -> str:
    texto = valor.strip()
    if not texto:
        raise ValueError(f"El {nombre} es obligatorio.")
    return texto


def _texto_opcional(valor: str | None) -> str | None:
    if valor is None:
        return None
    texto = valor.strip()
    return texto or None


def _flag_documental(valor: int, nombre: str) -> int:
    if valor not in (0, 1):
        raise ValueError(f"El flag de {nombre} debe ser 0 o 1.")
    return valor


def crear_factura(
    id_tutor: int,
    conceptos: list[ConceptoFacturable],
    fecha_vencimiento: date | None = None,
    metodo_pago: str = "Efectivo",
) -> Factura:
    """Crear una factura aplicando descuentos del catálogo por matrícula."""
    if not conceptos:
        raise ValueError("La factura debe incluir al menos un concepto.")

    tutor = db.session.get(Tutor, id_tutor)
    if tutor is None:
        raise ValueError("No existe el tutor indicado.")

    factura = Factura(
        tutor=tutor,
        fecha_vencimiento=fecha_vencimiento,
        metodo_pago=metodo_pago,
    )
    db.session.add(factura)
    total = Decimal("0.00")

    try:
        for concepto in conceptos:
            base = _importe_no_negativo(concepto.monto_base, "monto base")
            mora = _importe_no_negativo(concepto.recargo_mora, "recargo por mora")
            matricula = db.session.get(Matricula, concepto.id_matricula)

            if matricula is None or matricula.alumno.id_tutor != id_tutor:
                raise ValueError("La matrícula no pertenece al tutor indicado.")
            if not concepto.concepto.strip():
                raise ValueError("Cada concepto debe tener una descripción.")

            descuento_tipo = matricula.descuento_tipo
            porcentaje = Decimal("0")
            if descuento_tipo is not None:
                if not descuento_tipo.activo:
                    raise ValueError("La matrícula tiene asignado un descuento inactivo.")
                porcentaje = Decimal(str(descuento_tipo.porcentaje))
                if porcentaje < 0 or porcentaje > 100:
                    raise ValueError("El porcentaje de descuento debe estar entre 0 y 100.")

            descuento = (base * porcentaje / Decimal("100")).quantize(
                CENTAVO,
                rounding=ROUND_HALF_UP,
            )
            importe_final = base - descuento + mora
            total += importe_final

            factura.detalles.append(
                DetalleFactura(
                    matricula=matricula,
                    concepto=concepto.concepto.strip(),
                    monto_base=float(base),
                    descuento_aplicado=float(descuento),
                    recargo_mora=float(mora),
                    monto_final=float(importe_final),
                )
            )

        factura.total_pagar = float(total.quantize(CENTAVO, rounding=ROUND_HALF_UP))
        db.session.flush()
        registrar_evento_auditoria(
            "factura.creada",
            "factura",
            factura.id,
            detalles={
                "cantidad_conceptos": len(factura.detalles),
                "resultado": "creada",
            },
        )
        db.session.commit()
        return factura
    except Exception:
        db.session.rollback()
        raise


def _importe_no_negativo(importe: Decimal, nombre: str) -> Decimal:
    try:
        valor = Decimal(str(importe)).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    except (ArithmeticError, ValueError) as error:
        raise ValueError(f"El {nombre} debe ser un importe válido.") from error
    if not valor.is_finite() or valor < 0:
        raise ValueError(f"El {nombre} debe ser un importe no negativo.")
    return valor