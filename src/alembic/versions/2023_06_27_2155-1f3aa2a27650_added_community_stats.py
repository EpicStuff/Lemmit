"""Added Community stats

Revision ID: 1f3aa2a27650
Revises: 5475f3355267
Create Date: 2023-06-27 21:55:46.115484

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1f3aa2a27650'
down_revision = '5475f3355267'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('community_stats',
        sa.Column('community_id', sa.Integer(), nullable=False),
        sa.Column('subscribers', sa.Integer(), nullable=False),
        sa.Column('posts_per_day', sa.Integer(), nullable=False),
        sa.Column('min_interval', sa.Integer(), nullable=False),
        sa.Column('last_update', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['community_id'], ['communities.id'], ),
        sa.PrimaryKeyConstraint('community_id')
    )


def downgrade() -> None:
    op.drop_table('community_stats')
