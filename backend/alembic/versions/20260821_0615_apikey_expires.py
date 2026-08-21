"""Add expires column to apikeys table.

Revision ID: 20260821_0615
Revises: 
Create Date: 2026-08-21 06:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260821_0615'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from sqlalchemy import inspect

    conn = op.get_bind()
    cols = [c["name"] for c in inspect(conn).get_columns("apikeys")]
    if "expires" in cols:
        return
    with op.batch_alter_table('apikeys', schema=None) as batch_op:
        batch_op.add_column(sa.Column('expires', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('apikeys', schema=None) as batch_op:
        batch_op.drop_column('expires')
