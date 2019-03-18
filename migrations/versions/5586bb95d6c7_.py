"""empty message

Revision ID: 5586bb95d6c7
Revises: 9c9bb0dd1fca
Create Date: 2019-03-18 13:25:25.921760

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5586bb95d6c7'
down_revision = '9c9bb0dd1fca'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('Option', sa.Column('position', sa.Integer(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('Option', 'position')
    # ### end Alembic commands ###