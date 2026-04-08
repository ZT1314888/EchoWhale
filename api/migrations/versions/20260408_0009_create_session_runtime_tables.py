"""create session runtime tables"""

from alembic import op
import sqlalchemy as sa


revision = "20260408_0009"
down_revision = "20260407_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "session_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_session_events_session_id", "session_events", ["session_id"])
    op.create_index("ix_session_events_event_type", "session_events", ["event_type"])
    op.create_index("ix_session_events_stage", "session_events", ["stage"])
    op.create_index("ix_session_events_created_at", "session_events", ["created_at"])

    op.create_table(
        "voice_session_facts",
        sa.Column("session_id", sa.String(length=64), primary_key=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("termination_reason", sa.String(length=64), nullable=True),
        sa.Column("transcript_turn_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("client_diagnostics", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_voice_session_facts_status", "voice_session_facts", ["status"])
    op.create_index("ix_voice_session_facts_updated_at", "voice_session_facts", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_voice_session_facts_updated_at", table_name="voice_session_facts")
    op.drop_index("ix_voice_session_facts_status", table_name="voice_session_facts")
    op.drop_table("voice_session_facts")

    op.drop_index("ix_session_events_created_at", table_name="session_events")
    op.drop_index("ix_session_events_stage", table_name="session_events")
    op.drop_index("ix_session_events_event_type", table_name="session_events")
    op.drop_index("ix_session_events_session_id", table_name="session_events")
    op.drop_table("session_events")
