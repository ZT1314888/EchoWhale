"""add session reviews and timestamps"""

from alembic import op
import sqlalchemy as sa


revision = "20260404_0004"
down_revision = "20260403_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "sessions",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "session_messages",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE sessions SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL")
    op.execute("UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL")
    op.execute(
        "UPDATE session_messages SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"
    )
    op.alter_column("sessions", "created_at", nullable=False)
    op.alter_column("sessions", "updated_at", nullable=False)
    op.alter_column("session_messages", "created_at", nullable=False)
    op.create_index("ix_sessions_updated_at", "sessions", ["updated_at"], unique=False)

    op.create_table(
        "session_reviews",
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("highlight", sa.Text(), nullable=False),
        sa.Column("next_try", sa.Text(), nullable=False),
        sa.Column("feedback", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id"),
    )


def downgrade() -> None:
    op.drop_table("session_reviews")
    op.drop_index("ix_sessions_updated_at", table_name="sessions")
    op.drop_column("session_messages", "created_at")
    op.drop_column("sessions", "updated_at")
    op.drop_column("sessions", "created_at")
