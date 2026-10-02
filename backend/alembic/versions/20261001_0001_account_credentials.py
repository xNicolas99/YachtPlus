"""Bind credentials to account incarnations and prevent TOTP replay."""
from alembic import op
import sqlalchemy as sa
import secrets

revision = "20261001_0001"
down_revision = "20260929_0001"
branch_labels = None
depends_on = None

def upgrade():
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("user")}
    if "auth_version" not in columns:
        with op.batch_alter_table("user") as batch:
            batch.add_column(sa.Column("auth_version", sa.String(64), nullable=True))
    table = sa.table("user", sa.column("id"), sa.column("auth_version"))
    for user_id in op.get_bind().execute(sa.select(table.c.id).where(sa.or_(table.c.auth_version.is_(None), table.c.auth_version == ""))).scalars():
        op.get_bind().execute(table.update().where(table.c.id == user_id).values(auth_version=secrets.token_hex(32)))
    version_info = next(c for c in sa.inspect(op.get_bind()).get_columns("user") if c["name"] == "auth_version")
    if version_info["nullable"]:
        with op.batch_alter_table("user") as batch:
            batch.alter_column("auth_version", existing_type=sa.String(64), nullable=False)
    if "otp_last_step" not in columns:
        with op.batch_alter_table("user") as batch:
            batch.add_column(sa.Column("otp_last_step", sa.Integer(), nullable=True))
    # Existing deployments stored SMTP credentials as plaintext. Upgrade
    # them with the same persistent key/salt used for 2FA before serving API.
    from api.utils.crypto import encrypt, decrypt
    smtp = sa.table("smtp_settings", sa.column("id"), sa.column("password"))
    rows = op.get_bind().execute(sa.select(smtp.c.id, smtp.c.password)).all() if "smtp_settings" in sa.inspect(op.get_bind()).get_table_names() else []
    for row in rows:
        if row.password and not row.password.startswith("v2:"):
            op.get_bind().execute(smtp.update().where(smtp.c.id == row.id)
                                 .values(password=encrypt(decrypt(row.password))))
    if op.get_bind().dialect.name == "postgresql":
        for table, column in [("jwt_token_blacklist", "expires"), ("apikeys", "created_at"), ("templates", "created_at"), ("templates", "updated_at")]:
            info = next(c for c in sa.inspect(op.get_bind()).get_columns(table) if c["name"] == column)
            if not getattr(info["type"], "timezone", False):
                op.alter_column(table, column, type_=sa.DateTime(timezone=True),
                                postgresql_using=f"{column} AT TIME ZONE 'UTC'")

def downgrade():
    with op.batch_alter_table("user") as batch:
        batch.drop_column("otp_last_step")
        batch.drop_column("auth_version")
