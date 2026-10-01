"""create scene_analyses cache table"""

import sqlalchemy as sa
from alembic import op

revision = "20260930_0010"
down_revision = "20260408_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scene_analyses",
        sa.Column("media_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("scene", sa.String(length=128), nullable=True),
        sa.Column("role", sa.String(length=128), nullable=True),
        sa.Column("opener", sa.Text(), nullable=True),
        sa.Column("visual_anchors", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("vocab_candidates", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("error_code", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["media_id"], ["media.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("media_id"),
    )
    op.create_index("ix_scene_analyses_status", "scene_analyses", ["status"])
    op.create_index("ix_scene_analyses_updated_at", "scene_analyses", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_scene_analyses_updated_at", table_name="scene_analyses")
    op.drop_index("ix_scene_analyses_status", table_name="scene_analyses")
    op.drop_table("scene_analyses")
