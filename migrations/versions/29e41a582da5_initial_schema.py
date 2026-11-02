"""Initial schema

Revision ID: 29e41a582da5
Revises:
Create Date: 2026-11-01

"""
from alembic import op
import sqlalchemy as sa


revision = "29e41a582da5"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "anio_lectivo",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("numero_ciclo", sa.Integer(), nullable=False),
        sa.Column("fecha_inicio", sa.Date(), nullable=False),
        sa.Column("fecha_fin", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("numero_ciclo"),
    )
    op.create_table(
        "asignatura",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nombre_materia", sa.String(length=150), nullable=False),
        sa.Column("carga_horaria", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "condicion_materia",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(length=30), nullable=False),
        sa.Column("nombre", sa.String(length=80), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("codigo"),
    )
    op.create_table(
        "descuento_tipo",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(length=50), nullable=False),
        sa.Column("nombre", sa.String(length=120), nullable=False),
        sa.Column("porcentaje", sa.Float(), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("codigo"),
    )
    op.create_table(
        "docente",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=180), nullable=False),
        sa.Column("legajo_laboral", sa.String(length=50), nullable=False),
        sa.Column("especialidad", sa.String(length=150), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("legajo_laboral"),
    )
    op.create_table(
        "nivel_grado",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nombre_nivel", sa.String(length=100), nullable=False),
        sa.Column("grado_año", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "tutor",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=200), nullable=False),
        sa.Column("dni_cuit", sa.String(length=20), nullable=False),
        sa.Column("email", sa.String(length=200), nullable=True),
        sa.Column("telefono", sa.String(length=50), nullable=True),
        sa.Column("direccion", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dni_cuit"),
    )
    op.create_table(
        "alumno",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("id_tutor", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=120), nullable=False),
        sa.Column("apellido", sa.String(length=120), nullable=False),
        sa.Column("dni", sa.String(length=20), nullable=False),
        sa.Column("fecha_nacimiento", sa.Date(), nullable=True),
        sa.Column("legajo", sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(["id_tutor"], ["tutor.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dni"),
        sa.UniqueConstraint("legajo"),
    )
    op.create_table(
        "ciclo_escolar",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("id_anio", sa.Integer(), nullable=False),
        sa.Column("id_nivel", sa.Integer(), nullable=True),
        sa.Column("fecha_apertura", sa.Date(), nullable=False),
        sa.Column("fecha_cierre", sa.Date(), nullable=False),
        sa.CheckConstraint(
            "fecha_cierre >= fecha_apertura",
            name="ck_ciclo_escolar_fechas",
        ),
        sa.ForeignKeyConstraint(["id_anio"], ["anio_lectivo.id"]),
        sa.ForeignKeyConstraint(["id_nivel"], ["nivel_grado.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id_anio", "id_nivel", name="uq_ciclo_escolar_anio_nivel"),
    )
    op.create_table(
        "factura",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("id_tutor", sa.Integer(), nullable=False),
        sa.Column("fecha_emision", sa.Date(), nullable=False),
        sa.Column("fecha_vencimiento", sa.Date(), nullable=True),
        sa.Column("total_pagar", sa.Float(), nullable=False),
        sa.Column("metodo_pago", sa.String(length=30), nullable=False),
        sa.Column("estado_pago", sa.String(length=30), nullable=False),
        sa.ForeignKeyConstraint(["id_tutor"], ["tutor.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "grupo_seccion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("id_nivel", sa.Integer(), nullable=False),
        sa.Column("seccion", sa.String(length=50), nullable=False),
        sa.Column("capacidad_maxima", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["id_nivel"], ["nivel_grado.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "aspirante_crm",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("id_alumno", sa.Integer(), nullable=True),
        sa.Column("id_anio", sa.Integer(), nullable=True),
        sa.Column("id_nivel", sa.Integer(), nullable=True),
        sa.Column("nombre", sa.String(length=120), nullable=False),
        sa.Column("apellido", sa.String(length=120), nullable=False),
        sa.Column("dni", sa.String(length=20), nullable=False),
        sa.Column("fecha_nacimiento", sa.Date(), nullable=False),
        sa.Column("legajo", sa.String(length=50), nullable=True),
        sa.Column("nombre_tutor", sa.String(length=200), nullable=False),
        sa.Column("dni_cuit_tutor", sa.String(length=20), nullable=False),
        sa.Column("telefono_whatsapp", sa.String(length=50), nullable=True),
        sa.Column("email_tutor", sa.String(length=200), nullable=True),
        sa.Column("direccion_tutor", sa.String(length=255), nullable=True),
        sa.Column("curso_interes", sa.String(length=100), nullable=True),
        sa.Column("estado_entrevista", sa.String(length=80), nullable=True),
        sa.Column("estado", sa.String(length=30), nullable=False),
        sa.Column("fecha_registro", sa.Date(), nullable=False),
        sa.Column("partida_nacimiento", sa.Integer(), server_default="0", nullable=False),
        sa.Column("documento", sa.Integer(), server_default="0", nullable=False),
        sa.Column("certificado_primaria", sa.Integer(), server_default="0", nullable=False),
        sa.Column("pase_otra_escuela", sa.Integer(), server_default="0", nullable=False),
        sa.Column("libre_deuda", sa.Integer(), server_default="0", nullable=False),
        sa.Column("plan_estudio", sa.Integer(), server_default="0", nullable=False),
        sa.Column("libro_matriz", sa.Integer(), server_default="0", nullable=False),
        sa.Column("materias_adeudadas", sa.Integer(), server_default="0", nullable=False),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "certificado_primaria IN (0, 1)",
            name="ck_aspirante_certificado_primaria",
        ),
        sa.CheckConstraint("documento IN (0, 1)", name="ck_aspirante_documento"),
        sa.CheckConstraint("libre_deuda IN (0, 1)", name="ck_aspirante_libre_deuda"),
        sa.CheckConstraint("libro_matriz IN (0, 1)", name="ck_aspirante_libro_matriz"),
        sa.CheckConstraint(
            "materias_adeudadas IN (0, 1)",
            name="ck_aspirante_materias_adeudadas",
        ),
        sa.CheckConstraint(
            "partida_nacimiento IN (0, 1)",
            name="ck_aspirante_partida_nacimiento",
        ),
        sa.CheckConstraint(
            "pase_otra_escuela IN (0, 1)",
            name="ck_aspirante_pase_otra_escuela",
        ),
        sa.CheckConstraint("plan_estudio IN (0, 1)", name="ck_aspirante_plan_estudio"),
        sa.ForeignKeyConstraint(["id_alumno"], ["alumno.id"]),
        sa.ForeignKeyConstraint(["id_anio"], ["anio_lectivo.id"]),
        sa.ForeignKeyConstraint(["id_nivel"], ["nivel_grado.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id_alumno"),
    )
    op.create_table(
        "curso_direccion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("id_docente", sa.Integer(), nullable=False),
        sa.Column("id_asignatura", sa.Integer(), nullable=False),
        sa.Column("id_grupo", sa.Integer(), nullable=False),
        sa.Column("horario", sa.String(length=120), nullable=True),
        sa.ForeignKeyConstraint(["id_asignatura"], ["asignatura.id"]),
        sa.ForeignKeyConstraint(["id_docente"], ["docente.id"]),
        sa.ForeignKeyConstraint(["id_grupo"], ["grupo_seccion.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "matricula",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("id_alumno", sa.Integer(), nullable=False),
        sa.Column("id_anio", sa.Integer(), nullable=False),
        sa.Column("id_grupo", sa.Integer(), nullable=False),
        sa.Column("id_descuento", sa.Integer(), nullable=True),
        sa.Column("fecha_inscripcion", sa.Date(), nullable=False),
        sa.Column("estado", sa.String(length=50), nullable=False),
        sa.Column("repitente", sa.Integer(), server_default="0", nullable=False),
        sa.CheckConstraint("repitente IN (0, 1)", name="ck_matricula_repitente"),
        sa.ForeignKeyConstraint(["id_alumno"], ["alumno.id"]),
        sa.ForeignKeyConstraint(["id_anio"], ["anio_lectivo.id"]),
        sa.ForeignKeyConstraint(["id_descuento"], ["descuento_tipo.id"]),
        sa.ForeignKeyConstraint(["id_grupo"], ["grupo_seccion.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "asistencia",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("id_matricula", sa.Integer(), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("hora_llegada", sa.String(length=10), nullable=True),
        sa.Column("valor_falta", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["id_matricula"], ["matricula.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "calificacion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("id_matricula", sa.Integer(), nullable=False),
        sa.Column("id_curso_dir", sa.Integer(), nullable=False),
        sa.Column("diagnostico", sa.String(length=20), nullable=True),
        sa.Column("parcial_1", sa.String(length=20), nullable=True),
        sa.Column("parcial_2", sa.String(length=20), nullable=True),
        sa.Column("eval_trimestral", sa.String(length=20), nullable=True),
        sa.Column("recuperatorio", sa.String(length=20), nullable=True),
        sa.Column("nota_final", sa.String(length=20), nullable=True),
        sa.Column("periodo_evaluacion", sa.String(length=50), nullable=False),
        sa.ForeignKeyConstraint(["id_curso_dir"], ["curso_direccion.id"]),
        sa.ForeignKeyConstraint(["id_matricula"], ["matricula.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "certificado_medico",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("id_matricula", sa.Integer(), nullable=False),
        sa.Column("fecha_emision", sa.Date(), nullable=True),
        sa.Column("fecha_presentacion", sa.Date(), nullable=True),
        sa.Column("diagnostico_observacion", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["id_matricula"], ["matricula.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "detalle_factura",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("id_factura", sa.Integer(), nullable=False),
        sa.Column("id_matricula", sa.Integer(), nullable=False),
        sa.Column("concepto", sa.String(length=120), nullable=False),
        sa.Column("monto_base", sa.Float(), nullable=False),
        sa.Column("descuento_aplicado", sa.Float(), nullable=False),
        sa.Column("recargo_mora", sa.Float(), nullable=False),
        sa.Column("monto_final", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["id_factura"], ["factura.id"]),
        sa.ForeignKeyConstraint(["id_matricula"], ["matricula.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "inscripcion_materia",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("id_matricula", sa.Integer(), nullable=False),
        sa.Column("id_asignatura", sa.Integer(), nullable=False),
        sa.Column("id_condicion", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["id_asignatura"], ["asignatura.id"]),
        sa.ForeignKeyConstraint(["id_condicion"], ["condicion_materia.id"]),
        sa.ForeignKeyConstraint(["id_matricula"], ["matricula.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id_matricula", "id_asignatura", name="uq_inscripcion_materia"),
    )
    condiciones = sa.table(
        "condicion_materia",
        sa.column("id", sa.Integer()),
        sa.column("codigo", sa.String(length=30)),
        sa.column("nombre", sa.String(length=80)),
        sa.column("activo", sa.Boolean()),
    )
    op.bulk_insert(
        condiciones,
        [
            {"id": 1, "codigo": "APROBADO", "nombre": "Aprobado", "activo": True},
            {"id": 2, "codigo": "DESAPROBADO", "nombre": "Desaprobado", "activo": True},
            {"id": 3, "codigo": "LIBRE", "nombre": "Libre", "activo": True},
        ],
    )


def downgrade():
    op.drop_table("inscripcion_materia")
    op.drop_table("detalle_factura")
    op.drop_table("certificado_medico")
    op.drop_table("calificacion")
    op.drop_table("asistencia")
    op.drop_table("matricula")
    op.drop_table("curso_direccion")
    op.drop_table("aspirante_crm")
    op.drop_table("grupo_seccion")
    op.drop_table("factura")
    op.drop_table("ciclo_escolar")
    op.drop_table("alumno")
    op.drop_table("tutor")
    op.drop_table("nivel_grado")
    op.drop_table("docente")
    op.drop_table("descuento_tipo")
    op.drop_table("condicion_materia")
    op.drop_table("asignatura")
    op.drop_table("anio_lectivo")
