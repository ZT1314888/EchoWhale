"""drop media public_url column"""

from alembic import op
import sqlalchemy as sa


revision = "20260402_0002"
down_revision = "20260401_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("media") as batch_op:
        batch_op.drop_column("public_url")


def downgrade() -> None:
    with op.batch_alter_table("media") as batch_op:
        batch_op.add_column(
            sa.Column(
                "public_url",
                sa.String(length=1024),
                nullable=False,
                server_default="",
            )
        )

    with op.batch_alter_table("media") as batch_op:
        batch_op.alter_column("public_url", server_default=None)
