"""Persist opt-in Compose maintenance windows and their execution status."""

from alembic import op
import sqlalchemy as sa

revision = "20261027_0003"
down_revision = "20261027_0002"
branch_labels = None
depends_on = None


def upgrade():
    # Fresh databases register current models before historical migrations.
    from api.db.models.update_plans import UpdatePlan
    UpdatePlan.__table__.create(bind=op.get_bind(), checkfirst=True)


def downgrade():
    from api.db.models.update_plans import UpdatePlan
    UpdatePlan.__table__.drop(bind=op.get_bind(), checkfirst=True)
