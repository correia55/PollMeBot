"""empty message

Revision ID: 401185a6941b
Revises: efd984e900bd
Create Date: 2019-04-19 11:34:15.091179

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '401185a6941b'
down_revision = 'efd984e900bd'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('Poll', 'server_id', new_column_name='discord_server_id', existing_type=sa.String())
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('Poll', 'discord_server_id', new_column_name='server_id', existing_type=sa.String())
    # ### end Alembic commands ###