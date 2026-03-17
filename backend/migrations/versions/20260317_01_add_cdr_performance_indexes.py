"""Add CDR performance indexes for long-range dashboard queries

Revision ID: 20260317_01
Revises:
Create Date: 2026-03-17
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260317_01"
down_revision = None
branch_labels = None
depends_on = None


_INDEX_DEFS = (
    (
        "ix_cdr_cc_queue_joined_epoch",
        "cdr_records",
        ["cc_queue_joined_epoch"],
        sa.text("cc_queue_joined_epoch IS NOT NULL"),
    ),
    (
        "ix_cdr_cc_queue_answered_epoch",
        "cdr_records",
        ["cc_queue_answered_epoch"],
        sa.text("cc_queue_answered_epoch IS NOT NULL"),
    ),
    (
        "ix_cdr_cc_agent_uuid",
        "cdr_records",
        ["cc_agent_uuid"],
        sa.text("cc_agent_uuid IS NOT NULL"),
    ),
    (
        "ix_cdr_cc_agent",
        "cdr_records",
        ["cc_agent"],
        sa.text("cc_agent IS NOT NULL"),
    ),
    (
        "ix_cdr_extension_uuid",
        "cdr_records",
        ["extension_uuid"],
        sa.text("extension_uuid IS NOT NULL"),
    ),
    (
        "ix_cdr_cc_agent_start_epoch",
        "cdr_records",
        ["cc_agent", "start_epoch"],
        sa.text("cc_agent IS NOT NULL"),
    ),
    (
        "ix_cdr_cc_agent_uuid_start_epoch",
        "cdr_records",
        ["cc_agent_uuid", "start_epoch"],
        sa.text("cc_agent_uuid IS NOT NULL"),
    ),
    (
        "ix_cdr_start_epoch_direction_inbound",
        "cdr_records",
        ["start_epoch", "direction"],
        sa.text("direction = 'inbound'"),
    ),
)


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    if _is_postgres():
        ctx = op.get_context()
        with ctx.autocommit_block():
            for name, table_name, columns, where_clause in _INDEX_DEFS:
                op.create_index(
                    name,
                    table_name,
                    columns,
                    unique=False,
                    postgresql_where=where_clause,
                    postgresql_concurrently=True,
                    if_not_exists=True,
                )

        with ctx.autocommit_block():
            op.execute(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_cdr_start_epoch_brin "
                "ON cdr_records USING BRIN (start_epoch)"
            )
    else:
        for name, table_name, columns, where_clause in _INDEX_DEFS:
            op.create_index(
                name,
                table_name,
                columns,
                unique=False,
                postgresql_where=where_clause,
            )


def downgrade() -> None:
    if _is_postgres():
        ctx = op.get_context()
        with ctx.autocommit_block():
            op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_cdr_start_epoch_brin")
            for name, _, _, _ in reversed(_INDEX_DEFS):
                op.drop_index(name, table_name="cdr_records", postgresql_concurrently=True, if_exists=True)
    else:
        op.drop_index("ix_cdr_start_epoch_brin", table_name="cdr_records")
        for name, _, _, _ in reversed(_INDEX_DEFS):
            op.drop_index(name, table_name="cdr_records")
