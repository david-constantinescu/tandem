"""trip sharing: members and invite links

Revision ID: 9c4e1a7d5b20
Revises: 3f1d2a9b7c41
Create Date: 2026-11-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9c4e1a7d5b20"
down_revision = "3f1d2a9b7c41"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "trip_members",
        sa.Column("trip_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trip_id", "user_id", name="uq_trip_member"),
    )
    with op.batch_alter_table("trip_members", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_trip_members_trip_id"), ["trip_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_trip_members_user_id"), ["user_id"], unique=False)

    op.create_table(
        "trip_invites",
        sa.Column("trip_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("uses", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("trip_invites", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_trip_invites_trip_id"), ["trip_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_trip_invites_token_hash"), ["token_hash"], unique=True)


def downgrade():
    op.drop_table("trip_invites")
    op.drop_table("trip_members")
