from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy import Column, String, Integer, Boolean, ForeignKey


# Base class for DB Classes
base = declarative_base()


class Channel(base):
    __tablename__ = 'Channel'

    id = Column(Integer, primary_key=True)
    discord_id = Column(String, unique=True)
    delete_commands = Column(Boolean)
    delete_all = Column(Boolean)

    polls = relationship('Poll', cascade='all,delete')

    def __init__(self, discord_id, delete_commands=False, delete_all=False):
        self.discord_id = discord_id
        self.delete_commands = delete_commands
        self.delete_all = delete_all


class Poll(base):
    __tablename__ = 'Poll'

    id = Column(Integer, primary_key=True)
    poll_id = Column(String, unique=True)
    author = Column(String)
    question = Column(String)
    multiple_options = Column(Boolean)
    only_numbers = Column(Boolean)
    new_options = Column(Boolean)
    allow_external = Column(Boolean)
    message_id = Column(String)
    channel_id = Column(Integer, ForeignKey('Channel.id'))
    server_id = Column(String)

    options = relationship('Option', cascade='all,delete')

    def __init__(self, poll_id, author, question, multiple_options, only_numbers, new_options, allow_external, channel_id, server_id):
        self.poll_id = poll_id
        self.author = author
        self.question = question
        self.multiple_options = multiple_options
        self.only_numbers = only_numbers
        self.new_options = new_options
        self.allow_external = allow_external
        self.channel_id = channel_id
        self.server_id = server_id


class ClosedPoll(base):
    __tablename__ = 'ClosedPoll'

    id = Column(Integer, primary_key=True)
    poll_id = Column(String, unique=True)
    author = Column(String)
    message = Column(String)
    message_id = Column(String)
    channel_id = Column(Integer, ForeignKey('Channel.id'))
    server_id = Column(String)

    def __init__(self, poll_id, author, message, message_id, channel_id, server_id):
        self.poll_id = poll_id
        self.author = author
        self.message = message
        self.message_id = message_id
        self.channel_id = channel_id
        self.server_id = server_id


class Option(base):
    __tablename__ = 'Option'

    id = Column(Integer, primary_key=True)
    poll_id = Column(Integer, ForeignKey('Poll.id'))
    position = Column(Integer)
    option = Column(String)
    locked = Column(Boolean)

    votes = relationship('Vote', cascade='all,delete')

    def __init__(self, poll_id, position, option, locked=False):
        self.poll_id = poll_id
        self.position = position
        self.option = option
        self.locked = locked


class Vote(base):
    __tablename__ = 'Vote'

    id = Column(Integer, primary_key=True)
    option_id = Column(Integer, ForeignKey('Option.id'))
    participant_id = Column(String)
    participant_mention = Column(String)

    def __init__(self, option_id, participant_id, participant_mention):
        self.option_id = option_id
        self.participant_id = participant_id
        self.participant_mention = participant_mention
