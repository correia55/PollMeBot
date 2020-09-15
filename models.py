import datetime

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, Date, DateTime, UniqueConstraint, BigInteger

# Base class for DB Classes
base = declarative_base()


class Channel(base):
    __tablename__ = 'Channel'

    id = Column(Integer, primary_key=True)
    delete_commands = Column(Boolean)
    delete_all = Column(Boolean)

    discord_id = Column(BigInteger, unique=True)
    discord_server_id = Column(BigInteger)

    polls = relationship('Poll', cascade='all,delete')

    def __init__(self, discord_id, discord_server_id, delete_commands=False, delete_all=False):
        self.discord_id = discord_id
        self.discord_server_id = discord_server_id
        self.delete_commands = delete_commands
        self.delete_all = delete_all


class Poll(base):
    __tablename__ = 'Poll'

    id = Column(Integer, primary_key=True)
    created_datetime = Column(DateTime, default=datetime.datetime.utcnow)
    poll_key = Column(String)
    question = Column(String)
    multiple_options = Column(Boolean)
    only_numbers = Column(Boolean)
    new_options = Column(Boolean)
    allow_external = Column(Boolean)
    closed = Column(Boolean)
    closed_date = Column(Date)

    channel_id = Column(Integer, ForeignKey('Channel.id'))

    discord_server_id = Column(BigInteger)
    discord_author_id = Column(BigInteger)
    discord_message_id = Column(BigInteger, unique=True)

    __table_args__ = (UniqueConstraint('poll_key', 'discord_server_id', name='poll_composite_id'),)

    options = relationship('Option', cascade='all,delete')

    def __init__(self, poll_key, discord_author_id, question, multiple_options, only_numbers, new_options,
                 allow_external, channel_id, discord_server_id):
        self.poll_key = poll_key
        self.discord_author_id = discord_author_id
        self.question = question
        self.multiple_options = multiple_options
        self.only_numbers = only_numbers
        self.new_options = new_options
        self.allow_external = allow_external
        self.channel_id = channel_id
        self.discord_server_id = discord_server_id
        self.closed = False


class Option(base):
    __tablename__ = 'Option'

    id = Column(Integer, primary_key=True)
    position = Column(Integer)
    option_text = Column(String)
    locked = Column(Boolean)

    poll_id = Column(Integer, ForeignKey('Poll.id'))

    votes = relationship('Vote', cascade='all,delete')

    def __init__(self, poll_id, position, option_text, locked=False):
        self.poll_id = poll_id
        self.position = position
        self.option_text = option_text
        self.locked = locked


class Vote(base):
    __tablename__ = 'Vote'

    id = Column(Integer, primary_key=True)
    vote_datetime = Column(DateTime, default=datetime.datetime.utcnow)

    discord_participant_id = Column(BigInteger)
    participant_name = Column(String)

    option_id = Column(Integer, ForeignKey('Option.id'))

    def __init__(self, option_id, discord_participant_id, participant_name):
        self.option_id = option_id
        self.discord_participant_id = discord_participant_id
        self.participant_name = participant_name
