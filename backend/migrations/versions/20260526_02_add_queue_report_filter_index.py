"""Add partial index for queue performance report 30-day filter

Revision ID: 20260526_02
Revises: 20260317_01
Create Date: 2026-05-26
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260526_02"
down_revision = "20260317_01"
branch_labels = None
depends_on = None

_INDEX_NAME = "ix_cdr_queue_report_inbound_joined_start_epoch"
_TABLE_NAME = "cdr_records"


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if not _table_exists(_TABLE_NAME):
        return

    where_clause = sa.text("direction = 'inbound' AND cc_queue_joined_epoch IS NOT NULL")

    if _is_postgres():
        ctx = op.get_context()
        with ctx.autocommit_block():
            op.create_index(
                _INDEX_NAME,
                _TABLE_NAME,
                ["start_epoch"],
                unique=False,
                postgresql_where=where_clause,
                postgresql_concurrently=True,
                if_not_exists=True,
            )
    else:
        op.create_index(
            _INDEX_NAME,
            _TABLE_NAME,
            ["start_epoch"],
            unique=False,
            postgresql_where=where_clause,
        )


def downgrade() -> None:
    if not _table_exists(_TABLE_NAME):
        return

    if _is_postgres():
        ctx = op.get_context()
        with ctx.autocommit_block():
            op.drop_index(
                _INDEX_NAME,
                table_name=_TABLE_NAME,
                postgresql_concurrently=True,
                if_exists=True,
            )
    else:
        op.drop_index(_INDEX_NAME, table_name=_TABLE_NAME)
