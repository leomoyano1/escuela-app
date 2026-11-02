"""Add local accounts and append-only audit events.

Revision ID: ab41d879c562
Revises: 6fd8b6a2c41e
Create Date: 2026-11-01

"""
from alembic import op
import sqlalchemy as sa


revision = "ab41d879c562"
down_revision = "6fd8b6a2c41e"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "usuario",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_table(
        "evento_auditoria",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("ocurrido_en", sa.String(length=32), nullable=False),
        sa.Column("accion", sa.String(length=80), nullable=False),
        sa.Column("entidad", sa.String(length=80), nullable=False),
        sa.Column("entidad_id", sa.String(length=80), nullable=True),
        sa.Column("resultado", sa.String(length=20), nullable=False),
        sa.Column("detalles_json", sa.Text(), nullable=False),
        sa.Column("hash_anterior", sa.String(length=64), nullable=True),
        sa.Column("hash_evento", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["usuario.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hash_evento"),
    )
    op.create_index(
        "ix_evento_auditoria_actor_fecha",
        "evento_auditoria",
        ["actor_id", "ocurrido_en"],
    )
    op.create_index(
        "ix_evento_auditoria_entidad",
        "evento_auditoria",
        ["entidad", "entidad_id"],
    )
    op.execute(
        """
        CREATE TRIGGER evento_auditoria_no_update
        BEFORE UPDATE ON evento_auditoria
        BEGIN
            SELECT RAISE(ABORT, 'Los eventos de auditoría son inmutables.');
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER evento_auditoria_no_delete
        BEFORE DELETE ON evento_auditoria
        BEGIN
            SELECT RAISE(ABORT, 'Los eventos de auditoría no se pueden borrar.');
        END;
        """
    )


def downgrade():
    raise RuntimeError(
        "Las cuentas y la auditoría contienen datos de seguridad; "
        "restaura un respaldo previo en lugar de eliminarlos."
    )
