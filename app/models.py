from __future__ import annotations

from datetime import date, datetime, timezone

from flask_login import UserMixin
from sqlalchemy import Index, text
from werkzeug.security import check_password_hash, generate_password_hash

from .database import db


class Tutor(db.Model):
    """Representa al responsable financiero del alumno."""

    __tablename__ = "tutor"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False)
    dni_cuit = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(200), nullable=True)
    telefono = db.Column(db.String(50), nullable=True)
    direccion = db.Column(db.String(255), nullable=True)

    alumnos = db.relationship("Alumno", back_populates="tutor")
    facturas = db.relationship("Factura", back_populates="tutor")


class Usuario(UserMixin, db.Model):
    """Cuenta local con acceso uniforme a la aplicación escolar."""

    __tablename__ = "usuario"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default="1")
    creado_en = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    eventos_auditoria = db.relationship("EventoAuditoria", back_populates="actor")

    def get_id(self) -> str:
        return str(self.id)

    @property
    def is_active(self) -> bool:
        return self.activo

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class EventoAuditoria(db.Model):
    """Evento de auditoría local, encadenado criptográficamente y append-only."""

    __tablename__ = "evento_auditoria"
    __table_args__ = (
        db.Index("ix_evento_auditoria_actor_fecha", "actor_id", "ocurrido_en"),
        db.Index("ix_evento_auditoria_entidad", "entidad", "entidad_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(
        db.Integer,
        db.ForeignKey("usuario.id", ondelete="SET NULL"),
        nullable=True,
    )
    ocurrido_en = db.Column(db.String(32), nullable=False)
    accion = db.Column(db.String(80), nullable=False)
    entidad = db.Column(db.String(80), nullable=False)
    entidad_id = db.Column(db.String(80), nullable=True)
    resultado = db.Column(db.String(20), nullable=False)
    detalles_json = db.Column(db.Text, nullable=False, default="{}")
    hash_anterior = db.Column(db.String(64), nullable=True)
    hash_evento = db.Column(db.String(64), nullable=False, unique=True)

    actor = db.relationship("Usuario", back_populates="eventos_auditoria")


class Alumno(db.Model):
    """Entidad académica principal del sistema escolar."""

    __tablename__ = "alumno"

    id = db.Column(db.Integer, primary_key=True)
    id_tutor = db.Column(db.Integer, db.ForeignKey("tutor.id"), nullable=False)
    nombre = db.Column(db.String(120), nullable=False)
    apellido = db.Column(db.String(120), nullable=False)
    dni = db.Column(db.String(20), unique=True, nullable=False)
    fecha_nacimiento = db.Column(db.Date, nullable=True)
    legajo = db.Column(db.String(50), unique=True, nullable=True)
    fecha_baja = db.Column(db.Date, nullable=True)
    motivo_baja = db.Column(db.Text, nullable=True)

    tutor = db.relationship("Tutor", back_populates="alumnos")
    matriculas = db.relationship("Matricula", back_populates="alumno")
    aspirante_origen = db.relationship("AspiranteCRM", back_populates="alumno", uselist=False)


class AnioLectivo(db.Model):
    """Año escolar operativo del colegio."""

    __tablename__ = "anio_lectivo"
    __table_args__ = (
        db.CheckConstraint(
            "fecha_fin >= fecha_inicio",
            name="ck_anio_lectivo_fechas",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    numero_ciclo = db.Column(db.Integer, unique=True, nullable=False)
    fecha_inicio = db.Column(db.Date, nullable=False)
    fecha_fin = db.Column(db.Date, nullable=False)

    matriculas = db.relationship("Matricula", back_populates="anio_lectivo")
    ciclos_escolares = db.relationship("CicloEscolar", back_populates="anio_lectivo")


class NivelGrado(db.Model):
    """Nivel académico del colegio (ej. Secundario / 1er Año)."""

    __tablename__ = "nivel_grado"

    id = db.Column(db.Integer, primary_key=True)
    nombre_nivel = db.Column(db.String(100), nullable=False)
    grado_año = db.Column(db.String(100), nullable=False)

    grupos = db.relationship("GrupoSeccion", back_populates="nivel")
    ciclos_escolares = db.relationship("CicloEscolar", back_populates="nivel")


class CicloEscolar(db.Model):
    """Período regular de cursada dentro de un año lectivo."""

    __tablename__ = "ciclo_escolar"
    __table_args__ = (
        db.UniqueConstraint("id_anio", "id_nivel", name="uq_ciclo_escolar_anio_nivel"),
        Index(
            "uq_ciclo_escolar_anio_global",
            "id_anio",
            unique=True,
            sqlite_where=text("id_nivel IS NULL"),
        ),
        db.CheckConstraint(
            "fecha_cierre >= fecha_apertura",
            name="ck_ciclo_escolar_fechas",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    id_anio = db.Column(db.Integer, db.ForeignKey("anio_lectivo.id"), nullable=False)
    id_nivel = db.Column(db.Integer, db.ForeignKey("nivel_grado.id"), nullable=True)
    fecha_apertura = db.Column(db.Date, nullable=False)
    fecha_cierre = db.Column(db.Date, nullable=False)

    anio_lectivo = db.relationship("AnioLectivo", back_populates="ciclos_escolares")
    nivel = db.relationship("NivelGrado", back_populates="ciclos_escolares")


class GrupoSeccion(db.Model):
    """División o sección por grupo dentro de un nivel."""

    __tablename__ = "grupo_seccion"
    __table_args__ = (
        db.UniqueConstraint("id_nivel", "seccion", name="uq_grupo_nivel_seccion"),
        db.Index(
            "uq_grupo_nivel_sin_seccion",
            "id_nivel",
            unique=True,
            sqlite_where=text("seccion IS NULL"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    id_nivel = db.Column(db.Integer, db.ForeignKey("nivel_grado.id"), nullable=False)
    seccion = db.Column(db.String(50), nullable=True)
    capacidad_maxima = db.Column(db.Integer, nullable=False, default=30)

    nivel = db.relationship("NivelGrado", back_populates="grupos")
    matriculas = db.relationship("Matricula", back_populates="grupo")
    curso_direcciones = db.relationship("CursoDireccion", back_populates="grupo")
    historial_matriculas = db.relationship("HistorialGrupoMatricula", back_populates="grupo")


class DescuentoTipo(db.Model):
    """Catálogo de tipos de descuento aplicables a una matrícula."""

    __tablename__ = "descuento_tipo"

    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), unique=True, nullable=False)
    nombre = db.Column(db.String(120), nullable=False)
    porcentaje = db.Column(db.Float, nullable=False, default=0.0)
    descripcion = db.Column(db.Text, nullable=True)
    activo = db.Column(db.Boolean, nullable=False, default=True)

    matriculas = db.relationship("Matricula", back_populates="descuento_tipo")


class CondicionMateria(db.Model):
    """Catálogo estable de condiciones académicas por materia."""

    __tablename__ = "condicion_materia"

    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(30), unique=True, nullable=False)
    nombre = db.Column(db.String(80), nullable=False)
    activo = db.Column(db.Boolean, nullable=False, default=True)

    inscripciones = db.relationship("InscripcionMateria", back_populates="condicion")


class Matricula(db.Model):
    """Registro histórico del alumno en un año y grupo determinados."""

    __tablename__ = "matricula"
    __table_args__ = (
        db.UniqueConstraint(
            "id_alumno",
            "id_anio",
            name="uq_matricula_alumno_anio",
        ),
        db.CheckConstraint("repitente IN (0, 1)", name="ck_matricula_repitente"),
    )

    id = db.Column(db.Integer, primary_key=True)
    id_alumno = db.Column(db.Integer, db.ForeignKey("alumno.id"), nullable=False)
    id_anio = db.Column(db.Integer, db.ForeignKey("anio_lectivo.id"), nullable=False)
    id_grupo = db.Column(db.Integer, db.ForeignKey("grupo_seccion.id"), nullable=False)
    id_descuento = db.Column(db.Integer, db.ForeignKey("descuento_tipo.id"), nullable=True)
    fecha_inscripcion = db.Column(db.Date, nullable=False, default=date.today)
    estado = db.Column(db.String(50), nullable=False, default="Activa")
    fecha_baja = db.Column(db.Date, nullable=True)
    motivo_baja = db.Column(db.Text, nullable=True)
    repitente = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    alumno = db.relationship("Alumno", back_populates="matriculas")
    anio_lectivo = db.relationship("AnioLectivo", back_populates="matriculas")
    grupo = db.relationship("GrupoSeccion", back_populates="matriculas")
    historial_grupos = db.relationship(
        "HistorialGrupoMatricula",
        back_populates="matricula",
        order_by="HistorialGrupoMatricula.fecha_desde",
    )
    descuento_tipo = db.relationship("DescuentoTipo", back_populates="matriculas")

    calificaciones = db.relationship("Calificacion", back_populates="matricula")
    inscripciones_materia = db.relationship(
        "InscripcionMateria",
        back_populates="matricula",
    )
    asistencias = db.relationship("Asistencia", back_populates="matricula")
    certificados = db.relationship("CertificadoMedico", back_populates="matricula")
    detalles_factura = db.relationship("DetalleFactura", back_populates="matricula")


class HistorialGrupoMatricula(db.Model):
    """Períodos de asignación de grupo dentro de una matrícula anual."""

    __tablename__ = "historial_grupo_matricula"
    __table_args__ = (
        db.CheckConstraint(
            "fecha_hasta IS NULL OR fecha_hasta >= fecha_desde",
            name="ck_historial_grupo_fechas",
        ),
        db.Index(
            "uq_historial_grupo_activo",
            "id_matricula",
            unique=True,
            sqlite_where=text("fecha_hasta IS NULL"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    id_matricula = db.Column(db.Integer, db.ForeignKey("matricula.id"), nullable=False)
    id_grupo = db.Column(db.Integer, db.ForeignKey("grupo_seccion.id"), nullable=False)
    fecha_desde = db.Column(db.Date, nullable=False)
    fecha_hasta = db.Column(db.Date, nullable=True)

    matricula = db.relationship("Matricula", back_populates="historial_grupos")
    grupo = db.relationship("GrupoSeccion", back_populates="historial_matriculas")


class Asignatura(db.Model):
    """Materias o cursos que puede dictar el colegio."""

    __tablename__ = "asignatura"

    id = db.Column(db.Integer, primary_key=True)
    nombre_materia = db.Column(db.String(150), nullable=False)
    carga_horaria = db.Column(db.Integer, nullable=False, default=0)

    curso_direcciones = db.relationship("CursoDireccion", back_populates="asignatura")
    inscripciones_materia = db.relationship("InscripcionMateria", back_populates="asignatura")


class InscripcionMateria(db.Model):
    """Relación entre una matrícula anual y una asignatura."""

    __tablename__ = "inscripcion_materia"
    __table_args__ = (
        db.UniqueConstraint("id_matricula", "id_asignatura", name="uq_inscripcion_materia"),
    )

    id = db.Column(db.Integer, primary_key=True)
    id_matricula = db.Column(db.Integer, db.ForeignKey("matricula.id"), nullable=False)
    id_asignatura = db.Column(db.Integer, db.ForeignKey("asignatura.id"), nullable=False)
    id_condicion = db.Column(db.Integer, db.ForeignKey("condicion_materia.id"), nullable=True)

    matricula = db.relationship("Matricula", back_populates="inscripciones_materia")
    asignatura = db.relationship("Asignatura", back_populates="inscripciones_materia")
    condicion = db.relationship("CondicionMateria", back_populates="inscripciones")
    intentos_calificacion = db.relationship(
        "IntentoCalificacion",
        back_populates="inscripcion_materia",
        order_by="IntentoCalificacion.id",
    )


class Docente(db.Model):
    """Personal docente del establecimiento."""

    __tablename__ = "docente"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(180), nullable=False)
    legajo_laboral = db.Column(db.String(50), unique=True, nullable=False)
    especialidad = db.Column(db.String(150), nullable=True)

    curso_direcciones = db.relationship("CursoDireccion", back_populates="docente")


class CursoDireccion(db.Model):
    """Asigna un docente a una materia y grupo determinado."""

    __tablename__ = "curso_direccion"

    id = db.Column(db.Integer, primary_key=True)
    id_docente = db.Column(db.Integer, db.ForeignKey("docente.id"), nullable=False)
    id_asignatura = db.Column(db.Integer, db.ForeignKey("asignatura.id"), nullable=False)
    id_grupo = db.Column(db.Integer, db.ForeignKey("grupo_seccion.id"), nullable=False)
    horario = db.Column(db.String(120), nullable=True)

    docente = db.relationship("Docente", back_populates="curso_direcciones")
    asignatura = db.relationship("Asignatura", back_populates="curso_direcciones")
    grupo = db.relationship("GrupoSeccion", back_populates="curso_direcciones")

    calificaciones = db.relationship("Calificacion", back_populates="curso_direccion")


class Calificacion(db.Model):
    """Registro de evaluaciones por matrícula y curso."""

    __tablename__ = "calificacion"

    id = db.Column(db.Integer, primary_key=True)
    id_matricula = db.Column(db.Integer, db.ForeignKey("matricula.id"), nullable=False)
    id_curso_dir = db.Column(db.Integer, db.ForeignKey("curso_direccion.id"), nullable=False)
    diagnostico = db.Column(db.String(20), nullable=True)
    parcial_1 = db.Column(db.String(20), nullable=True)
    parcial_2 = db.Column(db.String(20), nullable=True)
    eval_trimestral = db.Column(db.String(20), nullable=True)
    recuperatorio = db.Column(db.String(20), nullable=True)
    nota_final = db.Column(db.String(20), nullable=True)
    periodo_evaluacion = db.Column(db.String(50), nullable=False, default="1° Trimestre")

    matricula = db.relationship("Matricula", back_populates="calificaciones")
    curso_direccion = db.relationship("CursoDireccion", back_populates="calificaciones")


class IntentoCalificacion(db.Model):
    """Intento trimestral inmutable, separado de la condición vigente."""

    __tablename__ = "intento_calificacion"
    __table_args__ = (
        db.CheckConstraint("trimestre IN (1, 2, 3)", name="ck_intento_calificacion_trimestre"),
        db.CheckConstraint(
            "tipo_evaluacion IN "
            "('DIAGNOSTICO', 'PARCIAL_1', 'PARCIAL_2', 'EVALUACION_TRIMESTRAL', "
            "'RECUPERATORIO', 'NOTA_FINAL')",
            name="ck_intento_calificacion_tipo",
        ),
        db.CheckConstraint(
            "valor IN ('A', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10')",
            name="ck_intento_calificacion_valor",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    id_inscripcion_materia = db.Column(
        db.Integer,
        db.ForeignKey("inscripcion_materia.id"),
        nullable=False,
        index=True,
    )
    trimestre = db.Column(db.Integer, nullable=False)
    tipo_evaluacion = db.Column(db.String(30), nullable=False)
    valor = db.Column(db.String(2), nullable=False)
    id_condicion_rendida = db.Column(
        db.Integer,
        db.ForeignKey("condicion_materia.id"),
        nullable=True,
    )
    actor_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    registrado_en = db.Column(db.DateTime(timezone=True), nullable=False)

    inscripcion_materia = db.relationship(
        "InscripcionMateria",
        back_populates="intentos_calificacion",
    )
    condicion_rendida = db.relationship("CondicionMateria")
    actor = db.relationship("Usuario")


class Asistencia(db.Model):
    """Asistencia diaria por alumno y matrícula."""

    __tablename__ = "asistencia"
    __table_args__ = (
        db.UniqueConstraint(
            "id_matricula",
            "fecha",
            name="uq_asistencia_matricula_fecha",
        ),
        db.CheckConstraint(
            "valor_falta IN (0, 0.5, 1)",
            name="ck_asistencia_valor_falta",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    id_matricula = db.Column(db.Integer, db.ForeignKey("matricula.id"), nullable=False)
    fecha = db.Column(db.Date, nullable=False, default=date.today)
    hora_llegada = db.Column(db.String(10), nullable=True)
    valor_falta = db.Column(db.Float, nullable=False, default=0.0)
    justificada = db.Column(db.Boolean, nullable=False, default=False, server_default="0")
    observaciones = db.Column(db.Text, nullable=True)
    justificada_por_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=True)
    justificada_en = db.Column(db.DateTime(timezone=True), nullable=True)

    matricula = db.relationship("Matricula", back_populates="asistencias")
    justificada_por = db.relationship("Usuario")
    notificaciones = db.relationship("NotificacionAsistencia", back_populates="asistencia")


class NotificacionAsistencia(db.Model):
    """Aviso interno generado al registrar una falta injustificada desde el umbral."""

    __tablename__ = "notificacion_asistencia"

    id = db.Column(db.Integer, primary_key=True)
    id_asistencia = db.Column(
        db.Integer,
        db.ForeignKey("asistencia.id"),
        nullable=False,
        index=True,
    )
    faltas_injustificadas = db.Column(db.Numeric(6, 1), nullable=False)
    generado_en = db.Column(db.DateTime(timezone=True), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)

    asistencia = db.relationship("Asistencia", back_populates="notificaciones")
    actor = db.relationship("Usuario")


class CertificadoMedico(db.Model):
    """Certificados médicos asociados a la matrícula del alumno."""

    __tablename__ = "certificado_medico"

    id = db.Column(db.Integer, primary_key=True)
    id_matricula = db.Column(db.Integer, db.ForeignKey("matricula.id"), nullable=False)
    fecha_emision = db.Column(db.Date, nullable=True)
    fecha_presentacion = db.Column(db.Date, nullable=True)
    diagnostico_observacion = db.Column(db.Text, nullable=True)

    matricula = db.relationship("Matricula", back_populates="certificados")


class Factura(db.Model):
    """Comprobante o recibo emitido a nombre del tutor."""

    __tablename__ = "factura"

    id = db.Column(db.Integer, primary_key=True)
    id_tutor = db.Column(db.Integer, db.ForeignKey("tutor.id"), nullable=False)
    fecha_emision = db.Column(db.Date, nullable=False, default=date.today)
    fecha_vencimiento = db.Column(db.Date, nullable=True)
    total_pagar = db.Column(db.Float, nullable=False, default=0.0)
    metodo_pago = db.Column(db.String(30), nullable=False, default="Efectivo")
    estado_pago = db.Column(db.String(30), nullable=False, default="Pendiente")

    tutor = db.relationship("Tutor", back_populates="facturas")
    detalles = db.relationship("DetalleFactura", back_populates="factura")


class DetalleFactura(db.Model):
    """Detalle de conceptos facturados por matrícula."""

    __tablename__ = "detalle_factura"

    id = db.Column(db.Integer, primary_key=True)
    id_factura = db.Column(db.Integer, db.ForeignKey("factura.id"), nullable=False)
    id_matricula = db.Column(db.Integer, db.ForeignKey("matricula.id"), nullable=False)
    concepto = db.Column(db.String(120), nullable=False)
    monto_base = db.Column(db.Float, nullable=False, default=0.0)
    descuento_aplicado = db.Column(db.Float, nullable=False, default=0.0)
    recargo_mora = db.Column(db.Float, nullable=False, default=0.0)
    monto_final = db.Column(db.Float, nullable=False, default=0.0)

    factura = db.relationship("Factura", back_populates="detalles")
    matricula = db.relationship("Matricula", back_populates="detalles_factura")


class AspiranteCRM(db.Model):
    """Datos precargados de una futura inscripción escolar."""

    __tablename__ = "aspirante_crm"

    id = db.Column(db.Integer, primary_key=True)
    id_alumno = db.Column(db.Integer, db.ForeignKey("alumno.id"), unique=True, nullable=True)
    id_anio = db.Column(db.Integer, db.ForeignKey("anio_lectivo.id"), nullable=True)
    id_nivel = db.Column(db.Integer, db.ForeignKey("nivel_grado.id"), nullable=True)

    nombre = db.Column(db.String(120), nullable=False)
    apellido = db.Column(db.String(120), nullable=False)
    dni = db.Column(db.String(20), nullable=False)
    fecha_nacimiento = db.Column(db.Date, nullable=False)
    legajo = db.Column(db.String(50), nullable=True)

    nombre_tutor = db.Column(db.String(200), nullable=False)
    dni_cuit_tutor = db.Column(db.String(20), nullable=False)
    telefono_whatsapp = db.Column(db.String(50), nullable=True)
    email_tutor = db.Column(db.String(200), nullable=True)
    direccion_tutor = db.Column(db.String(255), nullable=True)
    curso_interes = db.Column(db.String(100), nullable=True)
    estado_entrevista = db.Column(db.String(80), nullable=True)
    estado = db.Column(db.String(30), nullable=False, default="En espera")
    fecha_registro = db.Column(db.Date, nullable=False, default=date.today)
    fecha_baja = db.Column(db.Date, nullable=True)
    motivo_baja = db.Column(db.Text, nullable=True)

    partida_nacimiento = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    documento = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    certificado_primaria = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    pase_otra_escuela = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    libre_deuda = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    plan_estudio = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    libro_matriz = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    materias_adeudadas = db.Column(db.Integer, nullable=False, default=0, server_default="0")

    __table_args__ = (
        db.CheckConstraint("partida_nacimiento IN (0, 1)", name="ck_aspirante_partida_nacimiento"),
        db.CheckConstraint("documento IN (0, 1)", name="ck_aspirante_documento"),
        db.CheckConstraint("certificado_primaria IN (0, 1)", name="ck_aspirante_certificado_primaria"),
        db.CheckConstraint("pase_otra_escuela IN (0, 1)", name="ck_aspirante_pase_otra_escuela"),
        db.CheckConstraint("libre_deuda IN (0, 1)", name="ck_aspirante_libre_deuda"),
        db.CheckConstraint("plan_estudio IN (0, 1)", name="ck_aspirante_plan_estudio"),
        db.CheckConstraint("libro_matriz IN (0, 1)", name="ck_aspirante_libro_matriz"),
        db.CheckConstraint("materias_adeudadas IN (0, 1)", name="ck_aspirante_materias_adeudadas"),
    )

    observaciones = db.Column(db.Text, nullable=True)

    alumno = db.relationship("Alumno", back_populates="aspirante_origen")
    anio_lectivo = db.relationship("AnioLectivo")
    nivel = db.relationship("NivelGrado")
