"""create sessions tables"""

from alembic import op
import sqlalchemy as sa


revision = "20260403_0003"
down_revision = "20260402_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("media_id", sa.String(length=64), nullable=False),
        sa.Column("scene", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=128), nullable=False),
        sa.Column("opener", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("labels", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"], unique=False)
    op.create_index("ix_sessions_media_id", "sessions", ["media_id"], unique=False)
    op.create_index("ix_sessions_status", "sessions", ["status"], unique=False)

    op.create_table(
        "session_messages",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("feedback", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_session_messages_session_id", "session_messages", ["session_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_session_messages_session_id", table_name="session_messages")
    op.drop_table("session_messages")

    op.drop_index("ix_sessions_status", table_name="sessions")
    op.drop_index("ix_sessions_media_id", table_name="sessions")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
