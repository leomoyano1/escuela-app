"""Add auditable daily attendance and internal absence notifications.

Revision ID: df49b2a7c103
Revises: c51d7a2e9f04
Create Date: 2026-11-01

"""
from alembic import op
import sqlalchemy as sa


revision = "df49b2a7c103"
down_revision = "c51d7a2e9f04"
branch_labels = None
depends_on = None


def upgrade():
    conexion = op.get_bind()
    valor_invalido = conexion.execute(
        sa.text(
            "SELECT id, valor_falta FROM asistencia "
            "WHERE valor_falta NOT IN (0, 0.5, 1) LIMIT 1"
        )
    ).first()
    if valor_invalido:
        raise RuntimeError(
            "No se puede migrar asistencia: el registro "
            f"{valor_invalido.id} tiene un valor fuera de 0, 0.5 o 1. "
            "Revisá el dato conservando el historial y reintentá."
        )

    duplicada = conexion.execute(
        sa.text(
            """
            SELECT id_matricula, fecha, COUNT(*) AS cantidad
            FROM asistencia
            GROUP BY id_matricula, fecha
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if duplicada:
        raise RuntimeError(
            "No se puede garantizar una asistencia diaria por matrícula: "
            f"hay duplicados para la matrícula {duplicada.id_matricula} "
            f"y la fecha {duplicada.fecha}. Conservá el historial y resolvé "
            "el duplicado antes de reintentar."
        )

    with op.batch_alter_table("asistencia", recreate="always") as batch:
        batch.add_column(
            sa.Column(
                "justificada",
                sa.Boolean(),
                server_default=sa.text("0"),
                nullable=False,
            )
        )
        batch.add_column(sa.Column("observaciones", sa.Text(), nullable=True))
        batch.add_column(sa.Column("justificada_por_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("justificada_en", sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key(
            "fk_asistencia_justificada_por",
            "usuario",
            ["justificada_por_id"],
            ["id"],
        )
        batch.create_check_constraint(
            "ck_asistencia_valor_falta",
            "valor_falta IN (0, 0.5, 1)",
        )
        batch.create_unique_constraint(
            "uq_asistencia_matricula_fecha",
            ["id_matricula", "fecha"],
        )

    op.create_table(
        "notificacion_asistencia",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("id_asistencia", sa.Integer(), nullable=False),
        sa.Column("faltas_injustificadas", sa.Numeric(6, 1), nullable=False),
        sa.Column("generado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["usuario.id"]),
        sa.ForeignKeyConstraint(["id_asistencia"], ["asistencia.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notificacion_asistencia_id_asistencia",
        "notificacion_asistencia",
        ["id_asistencia"],
    )


def downgrade():
    raise RuntimeError(
        "La migración contiene historial de asistencia y notificaciones. "
        "Restaura un respaldo anterior en lugar de eliminarlos."
    )
