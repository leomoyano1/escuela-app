from __future__ import annotations

from datetime import date, datetime

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

    alumnos = db.relationship("Alumno", back_populates="tutor", cascade="all, delete-orphan")
    facturas = db.relationship("Factura", back_populates="tutor")


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

    tutor = db.relationship("Tutor", back_populates="alumnos")
    matriculas = db.relationship("Matricula", back_populates="alumno", cascade="all, delete-orphan")


class AnioLectivo(db.Model):
    """Año escolar operativo del colegio."""

    __tablename__ = "anio_lectivo"

    id = db.Column(db.Integer, primary_key=True)
    numero_ciclo = db.Column(db.Integer, unique=True, nullable=False)
    fecha_inicio = db.Column(db.Date, nullable=False)
    fecha_fin = db.Column(db.Date, nullable=False)

    matriculas = db.relationship("Matricula", back_populates="anio_lectivo")


class NivelGrado(db.Model):
    """Nivel académico del colegio (ej. Secundario / 1er Año)."""

    __tablename__ = "nivel_grado"

    id = db.Column(db.Integer, primary_key=True)
    nombre_nivel = db.Column(db.String(100), nullable=False)
    grado_año = db.Column(db.String(100), nullable=False)

    grupos = db.relationship("GrupoSeccion", back_populates="nivel")


class GrupoSeccion(db.Model):
    """División o sección por grupo dentro de un nivel."""

    __tablename__ = "grupo_seccion"

    id = db.Column(db.Integer, primary_key=True)
    id_nivel = db.Column(db.Integer, db.ForeignKey("nivel_grado.id"), nullable=False)
    seccion = db.Column(db.String(50), nullable=False)
    capacidad_maxima = db.Column(db.Integer, nullable=False, default=30)

    nivel = db.relationship("NivelGrado", back_populates="grupos")
    matriculas = db.relationship("Matricula", back_populates="grupo")
    curso_direcciones = db.relationship("CursoDireccion", back_populates="grupo")


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

    id = db.Column(db.Integer, primary_key=True)
    id_alumno = db.Column(db.Integer, db.ForeignKey("alumno.id"), nullable=False)
    id_anio = db.Column(db.Integer, db.ForeignKey("anio_lectivo.id"), nullable=False)
    id_grupo = db.Column(db.Integer, db.ForeignKey("grupo_seccion.id"), nullable=False)
    id_descuento = db.Column(db.Integer, db.ForeignKey("descuento_tipo.id"), nullable=True)
    fecha_inscripcion = db.Column(db.Date, nullable=False, default=date.today)
    estado = db.Column(db.String(50), nullable=False, default="Activa")

    alumno = db.relationship("Alumno", back_populates="matriculas")
    anio_lectivo = db.relationship("AnioLectivo", back_populates="matriculas")
    grupo = db.relationship("GrupoSeccion", back_populates="matriculas")
    descuento_tipo = db.relationship("DescuentoTipo", back_populates="matriculas")

    calificaciones = db.relationship("Calificacion", back_populates="matricula", cascade="all, delete-orphan")
    inscripciones_materia = db.relationship(
        "InscripcionMateria",
        back_populates="matricula",
        cascade="all, delete-orphan",
    )
    asistencias = db.relationship("Asistencia", back_populates="matricula", cascade="all, delete-orphan")
    certificados = db.relationship("CertificadoMedico", back_populates="matricula", cascade="all, delete-orphan")
    detalles_factura = db.relationship("DetalleFactura", back_populates="matricula")


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

    calificaciones = db.relationship("Calificacion", back_populates="curso_direccion", cascade="all, delete-orphan")


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


class Asistencia(db.Model):
    """Asistencia diaria por alumno y matrícula."""

    __tablename__ = "asistencia"

    id = db.Column(db.Integer, primary_key=True)
    id_matricula = db.Column(db.Integer, db.ForeignKey("matricula.id"), nullable=False)
    fecha = db.Column(db.Date, nullable=False, default=date.today)
    hora_llegada = db.Column(db.String(10), nullable=True)
    valor_falta = db.Column(db.Float, nullable=False, default=0.0)

    matricula = db.relationship("Matricula", back_populates="asistencias")


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
    detalles = db.relationship("DetalleFactura", back_populates="factura", cascade="all, delete-orphan")


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
    """Fichas de familias aspirantes para admisiones."""

    __tablename__ = "aspirante_crm"

    id = db.Column(db.Integer, primary_key=True)
    nombre_tutor = db.Column(db.String(200), nullable=False)
    telefono_whatsapp = db.Column(db.String(50), nullable=True)
    curso_interes = db.Column(db.String(100), nullable=True)
    estado_entrevista = db.Column(db.String(80), nullable=True)
    observaciones = db.Column(db.Text, nullable=True)
