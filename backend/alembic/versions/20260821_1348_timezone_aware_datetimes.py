"""Make DateTime columns timezone-aware.

Revision ID: 20260821_1348
Revises: 20260821_0615
Create Date: 2026-08-21 13:48:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260821_1348'
down_revision: Union[str, None] = '20260821_0615'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Columns changed from sa.DateTime() to sa.DateTime(timezone=True).
# SQLite stores timezone-agnostic strings either way, so the migration is
# mainly for PostgreSQL/MySQL correctness. The Python side now writes
# timezone-aware UTC values, making the schema match the code.
TABLE_COLUMNS = [
    ("templates", "created_at"),
    ("templates", "updated_at"),
    ("apikeys", "created_at"),
    ("apikeys", "expires"),
    ("login_attempts", "timestamp"),
]


def upgrade() -> None:
    for table, column in TABLE_COLUMNS:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.alter_column(
                column,
                existing_type=sa.DateTime(),
                type_=sa.DateTime(timezone=True),
                existing_nullable=True,
            )


def downgrade() -> None:
    for table, column in TABLE_COLUMNS:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.alter_column(
                column,
                existing_type=sa.DateTime(timezone=True),
                type_=sa.DateTime(),
                existing_nullable=True,
            )
