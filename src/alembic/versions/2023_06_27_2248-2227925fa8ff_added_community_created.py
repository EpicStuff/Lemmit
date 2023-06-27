"""Added Community.created

Revision ID: 2227925fa8ff
Revises: 1f3aa2a27650
Create Date: 2023-06-27 22:48:16.045730

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2227925fa8ff'
down_revision = '1f3aa2a27650'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('communities', sa.Column('created', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('communities', 'created')
