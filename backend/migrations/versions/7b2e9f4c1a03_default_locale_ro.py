"""Romanian is the default interface language for new accounts.

Revision ID: 7b2e9f4c1a03
Revises: 0c5414fd1de0
Create Date: 2026-10-31
"""
import sqlalchemy as sa
from alembic import op

revision = "7b2e9f4c1a03"
down_revision = "0c5414fd1de0"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch:
        batch.alter_column("locale", existing_type=sa.String(length=10), server_default="ro")


def downgrade():
    with op.batch_alter_table("users") as batch:
        batch.alter_column("locale", existing_type=sa.String(length=10), server_default=None)
