"""Persist operation status without storing operation credentials or payloads."""

from alembic import op
import sqlalchemy as sa
import uuid

revision = "20261027_0001"
down_revision = "20261001_0001"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {column["name"]: column for column in sa.inspect(bind).get_columns("user")}
    if "account_instance" not in columns:
        op.add_column("user", sa.Column("account_instance", sa.String(36), nullable=True))
    users = sa.table("user", sa.column("id", sa.Integer()), sa.column("account_instance", sa.String(36)))
    missing = bind.execute(sa.select(users.c.id).where(sa.or_(
        users.c.account_instance.is_(None), users.c.account_instance == "",
    ))).scalars().all()
    for user_id in missing:
        bind.execute(users.update().where(users.c.id == user_id).values(account_instance=str(uuid.uuid4())))
    current = {column["name"]: column for column in sa.inspect(bind).get_columns("user")}
    if current["account_instance"]["nullable"]:
        with op.batch_alter_table("user") as batch:
            batch.alter_column("account_instance", existing_type=sa.String(36), nullable=False)
    if "operation" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "operation",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("kind", sa.String(64), nullable=False),
            sa.Column("resource", sa.String(512), nullable=False),
            sa.Column("action", sa.String(32)),
            sa.Column("actor", sa.String(264), nullable=False),
            sa.Column("actor_id", sa.Integer(), nullable=False),
            sa.Column("actor_instance", sa.String(36), nullable=False),
            sa.Column("auth_version", sa.String(64)),
            sa.Column("retry_supported", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("worker_id", sa.String(36), nullable=False),
            sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("phase", sa.String(120), nullable=False),
            sa.Column("error", sa.Text()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True)),
            sa.Column("finished_at", sa.DateTime(timezone=True)),
        )
        for column in ("kind", "actor", "status", "worker_id"):
            op.create_index(f"ix_operation_{column}", "operation", [column])


def downgrade():
    op.drop_table("operation")
    with op.batch_alter_table("user") as batch:
        batch.drop_column("account_instance")
