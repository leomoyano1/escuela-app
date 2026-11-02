"""Validate school-year ranges and allow at most one global cycle per year.

Revision ID: 4a9e3cb713d1
Revises: ab41d879c562
Create Date: 2026-11-01

"""
from alembic import op
import sqlalchemy as sa


revision = "4a9e3cb713d1"
down_revision = "ab41d879c562"
branch_labels = None
depends_on = None


def upgrade():
    conexion = op.get_bind()
    anios_invalidos = conexion.execute(
        sa.text(
            "SELECT id FROM anio_lectivo WHERE fecha_fin < fecha_inicio LIMIT 1"
        )
    ).first()
    if anios_invalidos:
        raise RuntimeError(
            "No se puede migrar: hay un año lectivo con fecha_fin anterior a fecha_inicio."
        )

    ciclos_globales_duplicados = conexion.execute(
        sa.text(
            "SELECT id_anio FROM ciclo_escolar WHERE id_nivel IS NULL "
            "GROUP BY id_anio HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    if ciclos_globales_duplicados:
        raise RuntimeError(
            "No se puede migrar: hay más de un ciclo global para un año lectivo. "
            "Revise los registros antes de volver a ejecutar la migración."
        )

    with op.batch_alter_table("anio_lectivo") as batch:
        batch.create_check_constraint(
            "ck_anio_lectivo_fechas",
            "fecha_fin >= fecha_inicio",
        )

    op.create_index(
        "uq_ciclo_escolar_anio_global",
        "ciclo_escolar",
        ["id_anio"],
        unique=True,
        sqlite_where=sa.text("id_nivel IS NULL"),
    )


def downgrade():
    op.drop_index("uq_ciclo_escolar_anio_global", table_name="ciclo_escolar")
    with op.batch_alter_table("anio_lectivo") as batch:
        batch.drop_constraint("ck_anio_lectivo_fechas", type_="check")
