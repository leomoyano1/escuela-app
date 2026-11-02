"""Add immutable quarterly grade attempts without rewriting legacy grades.

Revision ID: c51d7a2e9f04
Revises: 81b5a7d209c4
Create Date: 2026-11-01

"""
from alembic import op
import sqlalchemy as sa


revision = "c51d7a2e9f04"
down_revision = "81b5a7d209c4"
branch_labels = None
depends_on = None


_CONDICIONES = (
    (1, "APROBADO", "Aprobado"),
    (2, "DESAPROBADO", "Desaprobado"),
    (3, "LIBRE", "Libre"),
)


def upgrade():
    conexion = op.get_bind()

    condiciones_existentes = conexion.execute(
        sa.text("SELECT id, codigo FROM condicion_materia")
    ).all()
    por_id = {fila.id: fila.codigo for fila in condiciones_existentes}
    por_codigo = {fila.codigo: fila.id for fila in condiciones_existentes}
    for id_condicion, codigo, nombre in _CONDICIONES:
        if id_condicion in por_id and por_id[id_condicion] != codigo:
            raise RuntimeError(
                "No se puede migrar calificaciones: el catálogo de condiciones "
                f"tiene el ID {id_condicion} asociado a {por_id[id_condicion]!r}; "
                f"se esperaba {codigo!r}. No se modificaron las notas históricas."
            )
        if codigo in por_codigo and por_codigo[codigo] != id_condicion:
            raise RuntimeError(
                "No se puede migrar calificaciones: el código de condición "
                f"{codigo!r} está asociado al ID {por_codigo[codigo]}; "
                f"se esperaba {id_condicion}. No se modificaron las notas históricas."
            )
        if id_condicion not in por_id:
            conexion.execute(
                sa.text(
                    "INSERT INTO condicion_materia (id, codigo, nombre, activo) "
                    "VALUES (:id, :codigo, :nombre, 1)"
                ),
                {"id": id_condicion, "codigo": codigo, "nombre": nombre},
            )

    duplicada = conexion.execute(
        sa.text(
            """
            SELECT id_matricula, id_asignatura, COUNT(*) AS cantidad
            FROM inscripcion_materia
            GROUP BY id_matricula, id_asignatura
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if duplicada:
        raise RuntimeError(
            "No se puede migrar la inscripción por materia: hay más de un registro "
            "para la misma matrícula y asignatura "
            f"(matrícula {duplicada.id_matricula}, asignatura "
            f"{duplicada.id_asignatura}). Resuelve el duplicado conservando el "
            "historial antes de reintentar; las calificaciones históricas no fueron "
            "modificadas."
        )

    constraints_unicos = sa.inspect(conexion).get_unique_constraints(
        "inscripcion_materia"
    )
    tiene_unicidad = any(
        set(constraint.get("column_names") or ())
        == {"id_matricula", "id_asignatura"}
        for constraint in constraints_unicos
    )
    if not tiene_unicidad:
        with op.batch_alter_table("inscripcion_materia", recreate="always") as batch:
            batch.create_unique_constraint(
                "uq_inscripcion_materia",
                ["id_matricula", "id_asignatura"],
            )

    # La tabla Calificacion histórica conserva todas sus filas y columnas: su
    # granularidad y los nombres de períodos no permiten una conversión inequívoca
    # a intentos trimestrales sin una regla institucional de correspondencia.
    op.create_table(
        "intento_calificacion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("id_inscripcion_materia", sa.Integer(), nullable=False),
        sa.Column("trimestre", sa.Integer(), nullable=False),
        sa.Column("tipo_evaluacion", sa.String(length=30), nullable=False),
        sa.Column("valor", sa.String(length=2), nullable=False),
        sa.Column("id_condicion_rendida", sa.Integer(), nullable=True),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column("registrado_en", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "trimestre IN (1, 2, 3)",
            name="ck_intento_calificacion_trimestre",
        ),
        sa.CheckConstraint(
            "tipo_evaluacion IN "
            "('DIAGNOSTICO', 'PARCIAL_1', 'PARCIAL_2', 'EVALUACION_TRIMESTRAL', "
            "'RECUPERATORIO', 'NOTA_FINAL')",
            name="ck_intento_calificacion_tipo",
        ),
        sa.CheckConstraint(
            "valor IN ('A', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10')",
            name="ck_intento_calificacion_valor",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["usuario.id"],
        ),
        sa.ForeignKeyConstraint(
            ["id_condicion_rendida"],
            ["condicion_materia.id"],
        ),
        sa.ForeignKeyConstraint(
            ["id_inscripcion_materia"],
            ["inscripcion_materia.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_intento_calificacion_id_inscripcion_materia",
        "intento_calificacion",
        ["id_inscripcion_materia"],
    )
    op.execute(
        """
        CREATE TRIGGER intento_calificacion_no_update
        BEFORE UPDATE ON intento_calificacion
        BEGIN
            SELECT RAISE(ABORT, 'Los intentos de calificación son inmutables.');
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER intento_calificacion_no_delete
        BEFORE DELETE ON intento_calificacion
        BEGIN
            SELECT RAISE(ABORT, 'Los intentos de calificación no se pueden borrar.');
        END;
        """
    )


def downgrade():
    raise RuntimeError(
        "Los intentos contienen historial académico. Restaura un respaldo anterior "
        "en lugar de eliminarlos."
    )
