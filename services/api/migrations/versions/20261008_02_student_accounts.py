"""Add student accounts without changing owner records or document history."""
from alembic import op
from sqlalchemy import inspect
from services.api.app.models import UserAccount

revision = "20261008_02"
down_revision = "20260901_01"
branch_labels = None
depends_on = None


def upgrade():
    UserAccount.__table__.create(bind=op.get_bind(), checkfirst=True)


def downgrade():
    if inspect(op.get_bind()).has_table("user_accounts"):
        op.drop_table("user_accounts")
