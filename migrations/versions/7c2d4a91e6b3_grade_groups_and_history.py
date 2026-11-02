"""Support unsectioned grades and preserve enrollment group periods.

Revision ID: 7c2d4a91e6b3
Revises: ab41d879c562
Create Date: 2026-11-01

"""
from alembic import op
import sqlalchemy as sa


revision = "7c2d4a91e6b3"
down_revision = "4a9e3cb713d1"
branch_labels = None
depends_on = None


def upgrade():
    conexion = op.get_bind()
    grupos_duplicados = conexion.execute(
        sa.text(
            """
            SELECT id_nivel, seccion, COUNT(*)
            FROM grupo_seccion
            GROUP BY id_nivel, seccion
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()
    grupos_sin_seccion_duplicados = conexion.execute(
        sa.text(
            """
            SELECT id_nivel, COUNT(*)
            FROM grupo_seccion
            WHERE seccion IS NULL OR trim(seccion) = ''
            GROUP BY id_nivel
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()
    grupos_sin_nivel = conexion.execute(
        sa.text(
            """
            SELECT grupo_seccion.id
            FROM grupo_seccion
            LEFT JOIN nivel_grado ON nivel_grado.id = grupo_seccion.id_nivel
            WHERE nivel_grado.id IS NULL
            LIMIT 1
            """
        )
    ).first()
    matriculas_sin_grupo = conexion.execute(
        sa.text(
            """
            SELECT matricula.id
            FROM matricula
            LEFT JOIN grupo_seccion ON grupo_seccion.id = matricula.id_grupo
            WHERE grupo_seccion.id IS NULL
            LIMIT 1
            """
        )
    ).first()
    if (
        grupos_duplicados
        or grupos_sin_seccion_duplicados
        or grupos_sin_nivel
        or matriculas_sin_grupo
    ):
        raise RuntimeError(
            "No se puede aplicar la migración académica: hay grupos duplicados "
            "por nivel/sección o relaciones de grupo/nivel inválidas. Revisá y "
            "resolvé esos datos antes de reintentar."
        )

    with op.batch_alter_table("grupo_seccion", recreate="always") as batch:
        batch.alter_column(
            "seccion",
            existing_type=sa.String(length=50),
            nullable=True,
        )
        batch.create_unique_constraint(
            "uq_grupo_nivel_seccion",
            ["id_nivel", "seccion"],
        )
        batch.create_index(
            "uq_grupo_nivel_sin_seccion",
            ["id_nivel"],
            unique=True,
            sqlite_where=sa.text("seccion IS NULL"),
        )
    conexion.execute(
        sa.text("UPDATE grupo_seccion SET seccion = NULL WHERE trim(seccion) = ''")
    )

    op.create_table(
        "historial_grupo_matricula",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("id_matricula", sa.Integer(), nullable=False),
        sa.Column("id_grupo", sa.Integer(), nullable=False),
        sa.Column("fecha_desde", sa.Date(), nullable=False),
        sa.Column("fecha_hasta", sa.Date(), nullable=True),
        sa.CheckConstraint(
            "fecha_hasta IS NULL OR fecha_hasta >= fecha_desde",
            name="ck_historial_grupo_fechas",
        ),
        sa.ForeignKeyConstraint(["id_grupo"], ["grupo_seccion.id"]),
        sa.ForeignKeyConstraint(["id_matricula"], ["matricula.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_historial_grupo_activo",
        "historial_grupo_matricula",
        ["id_matricula"],
        unique=True,
        sqlite_where=sa.text("fecha_hasta IS NULL"),
    )

    matriculas = conexion.execute(
        sa.text("SELECT id, id_grupo, fecha_inscripcion FROM matricula ORDER BY id")
    ).all()
    if matriculas:
        conexion.execute(
            sa.text(
                """
                INSERT INTO historial_grupo_matricula
                    (id_matricula, id_grupo, fecha_desde, fecha_hasta)
                VALUES (:id_matricula, :id_grupo, :fecha_desde, NULL)
                """
            ),
            [
                {
                    "id_matricula": fila.id,
                    "id_grupo": fila.id_grupo,
                    "fecha_desde": fila.fecha_inscripcion,
                }
                for fila in matriculas
            ],
        )

    op.execute(
        """
        CREATE TRIGGER historial_grupo_no_delete
        BEFORE DELETE ON historial_grupo_matricula
        BEGIN
            SELECT RAISE(ABORT, 'El historial de grupos no se puede borrar.');
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER historial_grupo_no_solapamiento_insert
        BEFORE INSERT ON historial_grupo_matricula
        WHEN EXISTS (
            SELECT 1
            FROM historial_grupo_matricula existente
            WHERE existente.id_matricula = NEW.id_matricula
              AND existente.fecha_desde <= COALESCE(NEW.fecha_hasta, '9999-12-31')
              AND COALESCE(existente.fecha_hasta, '9999-12-31') >= NEW.fecha_desde
        )
        BEGIN
            SELECT RAISE(ABORT, 'Los períodos de grupo no pueden solaparse.');
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER historial_grupo_no_solapamiento_update
        BEFORE UPDATE ON historial_grupo_matricula
        WHEN EXISTS (
            SELECT 1
            FROM historial_grupo_matricula existente
            WHERE existente.id_matricula = NEW.id_matricula
              AND existente.id != OLD.id
              AND existente.fecha_desde <= COALESCE(NEW.fecha_hasta, '9999-12-31')
              AND COALESCE(existente.fecha_hasta, '9999-12-31') >= NEW.fecha_desde
        )
        BEGIN
            SELECT RAISE(ABORT, 'Los períodos de grupo no pueden solaparse.');
        END;
        """
    )


def downgrade():
    raise RuntimeError(
        "Esta revisión incorpora historial de asignaciones. Restaura un respaldo "
        "anterior en lugar de eliminar períodos académicos."
    )
