"""create media table"""

from alembic import op
import sqlalchemy as sa


revision = "20260401_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "media",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("public_url", sa.String(length=1024), nullable=False),
        sa.Column("upload_status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_media_storage_key", "media", ["storage_key"], unique=True)
    op.create_index("ix_media_upload_status", "media", ["upload_status"], unique=False)
    op.create_index("ix_media_user_id", "media", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_media_user_id", table_name="media")
    op.drop_index("ix_media_upload_status", table_name="media")
    op.drop_index("ix_media_storage_key", table_name="media")
    op.drop_table("media")
