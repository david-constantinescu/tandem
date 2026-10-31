"""Conversations get a kind: the user's own chats, or the one where Tandem writes first.

Revision ID: 3f1d2a9b7c41
Revises: 7b2e9f4c1a03
Create Date: 2026-10-31
"""
import sqlalchemy as sa
from alembic import op

revision = "3f1d2a9b7c41"
down_revision = "7b2e9f4c1a03"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("conversations") as batch:
        batch.add_column(sa.Column("kind", sa.String(length=20), nullable=False, server_default="chat"))


def downgrade():
    with op.batch_alter_table("conversations") as batch:
        batch.drop_column("kind")
