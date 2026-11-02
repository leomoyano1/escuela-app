"""Enforce one annual enrollment per student.

Revision ID: 81b5a7d209c4
Revises: 7c2d4a91e6b3
Create Date: 2026-11-01

"""
from alembic import op
import sqlalchemy as sa


revision = "81b5a7d209c4"
down_revision = "7c2d4a91e6b3"
branch_labels = None
depends_on = None


def upgrade():
    conexion = op.get_bind()
    duplicada = conexion.execute(
        sa.text(
            """
            SELECT id_alumno, id_anio
            FROM matricula
            GROUP BY id_alumno, id_anio
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if duplicada:
        raise RuntimeError(
            "No se puede garantizar una matrícula anual única: hay más de una "
            "matrícula para el mismo alumno y año lectivo. Revisá esos registros "
            "antes de volver a ejecutar la migración."
        )

    with op.batch_alter_table("matricula") as batch:
        batch.create_unique_constraint(
            "uq_matricula_alumno_anio",
            ["id_alumno", "id_anio"],
        )


def downgrade():
    with op.batch_alter_table("matricula") as batch:
        batch.drop_constraint("uq_matricula_alumno_anio", type_="unique")
