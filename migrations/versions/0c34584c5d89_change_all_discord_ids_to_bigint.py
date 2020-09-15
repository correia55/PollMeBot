"""Change all discord ids to bigint

Revision ID: 0c34584c5d89
Revises: 9231c70363d9
Create Date: 2020-09-15 14:59:11.376467

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0c34584c5d89'
down_revision = '9231c70363d9'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column('Poll', 'discord_server_id')
    op.add_column('Poll', sa.Column('discord_server_id', sa.BigInteger(), autoincrement=False, nullable=True))
    op.drop_column('Poll', 'discord_author_id')
    op.add_column('Poll', sa.Column('discord_author_id', sa.BigInteger(), autoincrement=False, nullable=True))
    op.drop_column('Poll', 'discord_message_id')
    op.add_column('Poll', sa.Column('discord_message_id', sa.BigInteger(), autoincrement=False, nullable=True))
    op.drop_column('Vote', 'discord_participant_id')
    op.add_column('Vote', sa.Column('discord_participant_id', sa.BigInteger(), autoincrement=False, nullable=True))
    op.add_column('Vote', sa.Column('participant_name', sa.String(), autoincrement=False, nullable=True))


def downgrade():
    op.drop_column('Poll', 'discord_server_id')
    op.add_column('Poll', sa.Column('discord_server_id', sa.Integer(), autoincrement=False, nullable=True))
    op.drop_column('Poll', 'discord_author_id')
    op.add_column('Poll', sa.Column('discord_author_id', sa.Integer(), autoincrement=False, nullable=True))
    op.drop_column('Poll', 'discord_message_id')
    op.add_column('Poll', sa.Column('discord_message_id', sa.Integer(), autoincrement=False, nullable=True))
    op.drop_column('Vote', 'discord_participant_id')
    op.add_column('Vote', sa.Column('discord_participant_id', sa.Integer(), autoincrement=False, nullable=True))
    op.drop_column('Vote', 'participant_name')
