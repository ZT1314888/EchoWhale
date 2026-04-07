"""make session media_id nullable"""

from alembic import op


revision = "20260407_0008"
down_revision = "20260406_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.alter_column("media_id", existing_type=None, nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.alter_column("media_id", existing_type=None, nullable=False)
