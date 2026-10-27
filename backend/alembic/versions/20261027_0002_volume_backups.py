"""Add volume backup metadata and opt-in schedules."""
from alembic import op

revision = "20261027_0002"
down_revision = "20261027_0001"
branch_labels = None
depends_on = None


def upgrade():
    from api.db.models.backups import VolumeBackup, BackupSchedule
    VolumeBackup.__table__.create(op.get_bind(), checkfirst=True)
    BackupSchedule.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    from api.db.models.backups import VolumeBackup, BackupSchedule
    BackupSchedule.__table__.drop(op.get_bind(), checkfirst=True)
    VolumeBackup.__table__.drop(op.get_bind(), checkfirst=True)
