"""Reserve the first setup account atomically across workers.

Revision ID: 20260929_0001
Revises: 20260821_1348
"""

from alembic import op
import sqlalchemy as sa


revision = "20260929_0001"
down_revision = "20260821_1348"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # env.py creates current metadata for unversioned installs before
    # migrations run; a versioned deployment still needs this CREATE TABLE.
    if "setup_registration_claim" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "setup_registration_claim",
            sa.Column("id", sa.Integer(), primary_key=True),
        )


def downgrade() -> None:
    op.drop_table("setup_registration_claim")
