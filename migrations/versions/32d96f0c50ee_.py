"""empty message

Revision ID: 32d96f0c50ee
Revises: 77da8e2b32b7
Create Date: 2019-04-28 09:46:01.693418

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '32d96f0c50ee'
down_revision = '77da8e2b32b7'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('Vote', 'discord_participant_mention')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('Vote', sa.Column('discord_participant_mention', sa.VARCHAR(), autoincrement=False, nullable=True))
    # ### end Alembic commands ###