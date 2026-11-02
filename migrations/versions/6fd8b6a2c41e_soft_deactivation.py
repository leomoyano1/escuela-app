"""Add soft-deactivation metadata to student records.

Revision ID: 6fd8b6a2c41e
Revises: 29e41a582da5
Create Date: 2026-11-01

"""
from alembic import op
import sqlalchemy as sa


revision = "6fd8b6a2c41e"
down_revision = "29e41a582da5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("alumno", sa.Column("fecha_baja", sa.Date(), nullable=True))
    op.add_column("alumno", sa.Column("motivo_baja", sa.Text(), nullable=True))
    op.add_column("matricula", sa.Column("fecha_baja", sa.Date(), nullable=True))
    op.add_column("matricula", sa.Column("motivo_baja", sa.Text(), nullable=True))
    op.add_column("aspirante_crm", sa.Column("fecha_baja", sa.Date(), nullable=True))
    op.add_column("aspirante_crm", sa.Column("motivo_baja", sa.Text(), nullable=True))


def downgrade():
    raise RuntimeError(
        "Esta revisión contiene datos de bajas lógicas. Para retroceder, "
        "restaura un respaldo previo o crea una revisión de datos explícita."
    )
