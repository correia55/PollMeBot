import os
import discord
import asyncio

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy import Column, String, Integer, Boolean, ForeignKey


# region DB Classes

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
    message_id = Column(String)
    channel_id = Column(Integer, ForeignKey('Channel.id'))
    server_id = Column(String)

    options = relationship('Option', cascade='all,delete')

    def __init__(self, poll_id, author, question, multiple_options, only_numbers, new_options, channel_id, server_id):
        self.poll_id = poll_id
        self.author = author
        self.question = question
        self.multiple_options = multiple_options
        self.only_numbers = only_numbers
        self.new_options = new_options
        self.channel_id = channel_id
        self.server_id = server_id


class Option(base):
    __tablename__ = 'Option'

    id = Column(Integer, primary_key=True)
    poll_id = Column(Integer, ForeignKey('Poll.id'))
    option = Column(String)

    votes = relationship('Vote', cascade='all,delete')

    def __init__(self, poll_id, option):
        self.poll_id = poll_id
        self.option = option


class Vote(base):
    __tablename__ = 'Vote'

    id = Column(Integer, primary_key=True)
    option_id = Column(Integer, ForeignKey('Option.id'))
    participant_id = Column(String)

    def __init__(self, option_id, participant_id):
        self.option_id = option_id
        self.participant_id = participant_id

# endregion


# region Initialization

database_url = os.environ.get('DATABASE_URL', None)

if database_url is None:
    print('Unable to find database url!')
    exit(1)

engine = create_engine(database_url)
Session = sessionmaker(bind=engine)

# Create tables if they don't exist
if not engine.dialect.has_table(engine, 'Channel'):
    print('Creating Tables...')
    base.metadata.create_all(engine)

# New Session
session = Session()

# Get the token for the bot saved in the environment variable
token = os.environ.get('BOT_TOKEN', None)

if token is None:
    print('Unable to find bot token!')
    exit(1)

# Create a client
client = discord.Client()

# Time between checks for deleted messages and channels
CHECK_DELETED_WAIT_TIME = 43200

# Limit number of polls per server
POLL_LIMIT_SERVER = 10

# endregion


# region Events

# When the bot is ready to work
@client.event
async def on_ready():
    print('The bot is ready to poll!\n-------------------------')

    # Coroutine to check if the messages still exist
    await check_messages_exist()


# When a message is written in Discord
@client.event
async def on_message(message):
    # Get the channel information from the DB
    db_channel = session.query(Channel).filter(Channel.discord_id == message.channel.id).first()

    is_command = True

    # Check if it is a command and call the correct function to treat it
    if message.content.startswith('!poll_me_channel '):
        await configure_channel(message, db_channel)
    elif message.content.startswith('!poll_edit '):
        await edit_poll(message, db_channel)
    elif message.content.startswith('!poll_close '):
        await close_poll_command(message, db_channel)
    elif message.content.startswith('!poll_remove '):
        await remove_poll(message, db_channel)
    elif message.content.startswith('!poll '):
        await create_poll(message, db_channel)
    elif message.content.startswith('!vote '):
        await vote_poll(message, db_channel)
    elif message.content.startswith('!unvote '):
        await remove_vote(message, db_channel)
    elif message.content.startswith('!refresh '):
        await refresh_poll(message, db_channel)
    elif message.content.startswith('!help_me_poll'):
        await help_message(message, db_channel)
    else:
        is_command = False

    # Delete all messages or just commands, depending on the channel settings
    if db_channel is not None:
        try:
            # Delete all messages that were not sent by the bot
            if db_channel.delete_all and message.author != client.user:
                await client.delete_message(message)
            # Delete all messages associated with a command
            elif db_channel.delete_commands and is_command:
                await client.delete_message(message)
        except discord.errors.NotFound:
            pass

# endregion


# region Commands

async def configure_channel(command, db_channel):
    """
    Configure a channel with the given settings.
    If this channel does not yet exit in the DB, then create it.

    :param command: the command used.
    :param db_channel: the corresponding channel entry in the DB.
    """

    # Make sure the user changing the channel settings is an admin
    if not command.author.server_permissions.administrator:
        msg = 'Only server administrators can change a channel\'s settings.'

        await send_temp_message(msg, command.channel)
        return

    # The id of the Discord channel where the message was sent
    channel_id = command.channel.id

    # Get the list of parameters in the message
    params = parse_command_parameters(command.content)

    # If the command has an invalid number of parameters
    if len(params) != 2:
        return

    # Filter the chosen setting
    delete_commands = False
    delete_all = False

    if params[1] == '-dc':
        delete_commands = True
    elif params[1] == '-da':
        delete_all = True
    elif params[1] == '-ka':
        delete_all = False
        delete_commands = False

    # Create or modify the channel with the correct configurations
    if db_channel is None:
        db_channel = Channel(channel_id, delete_commands, delete_all)

        session.add(db_channel)
    else:
        db_channel.delete_commands = delete_commands
        db_channel.delete_all = delete_all

    session.commit()


async def create_poll(command, db_channel):
    """
    Create a new poll.

    :param command: the command used.
    :param db_channel: the corresponding channel entry in the DB.
    """

    # The id of the Discord channel where the message was sent
    channel_id = command.channel.id

    # The id of the Discord server where the message was sent
    server_id = command.server.id

    # Create channel if it does not already exist
    if db_channel is None:
        db_channel = Channel(channel_id)

        session.add(db_channel)

    # Get the list of parameters in the message
    params = parse_command_parameters(command.content)

    multiple_options = False
    only_numbers = False
    new_options = False

    # Confirmation is necessary when there is a need to close a poll before this one is created
    confirmation = False

    poll_params = []

    # Filter the available configurations for polls
    for i in range(len(params)):
        if i == 0:
            continue
        if params[i].startswith('-'):
            if params[i].__contains__('m'):
                multiple_options = True
            if params[i].__contains__('o'):
                only_numbers = True
            if params[i].__contains__('n'):
                new_options = True
            if params[i].__contains__('y'):
                confirmation = True
        else:
            # Add all non configuration parameters, ignoring quotation marks
            poll_params.append(params[i].replace('"', ''))

    # If the command has an invalid number of parameters
    if len(poll_params) < 2:
        msg = 'Invalid parameters in command: **%s**' % command.content

        await send_temp_message(msg, command.channel)
        return

    # Get the poll with this id
    poll = session.query(Poll).filter(Poll.poll_id == poll_params[0]).first()

    # If a poll with the same id already exists, close it
    if poll is not None:
        # Confirmation required before closing a poll
        if not confirmation:
            msg = 'A poll with that id already exists add **-y** to your command to confirm the closing of the ' \
                  'previous poll.\nYour command: **%s**' % command.content

            await send_temp_message(msg, command.channel)
            return

        # Get all options available in the poll
        options = session.query(Option).filter(Option.poll_id == poll.id).all()

        await close_poll(poll, db_channel, options, range(1, len(options) + 1))

    # Limit the number of polls per server
    while session.query(Poll).filter(Poll.server_id == server_id).count() >= POLL_LIMIT_SERVER:
        # Confirmation required before closing other polls
        if not confirmation:
            msg = 'The server you\'re in has reached its poll limit, creating another poll will force the closing of ' \
                  'the oldest poll still active. Add **-y** to your command to confirm the closing of the ' \
                  'previous poll.\nYour command: **%s**' % command.content

            await send_temp_message(msg, command.channel)
            return

        poll = session.query(Poll).filter(Poll.server_id == server_id).first()

        # Get all options available in the poll
        options = session.query(Option).filter(Option.poll_id == poll.id).all()

        await close_poll(poll, db_channel, options, range(1, len(options) + 1))

    # Create the new poll
    new_poll = Poll(poll_params[0], command.author.mention, poll_params[1], multiple_options, only_numbers, new_options,
                    db_channel.id, server_id)

    session.add(new_poll)

    # Necessary for the options to get the poll id
    session.flush()

    options = []

    # Create the options
    if len(poll_params[2:]) != 0:
        for option in poll_params[2:]:
            options.append(Option(new_poll.id, option))
    # If no options were provided, then create the default Yes and No
    else:
        options.append(Option(new_poll.id, 'Yes'))
        options.append(Option(new_poll.id, 'No'))

    session.add_all(options)

    # Create the message with the poll
    msg = await client.send_message(command.channel, create_message(new_poll, options))

    new_poll.message_id = msg.id

    session.commit()


async def edit_poll(command, db_channel):
    """
    Edit a poll.

    :param command: the command used.
    :param db_channel: the corresponding channel entry in the DB.
    """

    # If the channel does not exist in the DB
    if db_channel is None:
        msg = 'There\'s no poll in this channel for you to edit!'

        await send_temp_message(msg, command.channel)
        return

    # Get the list of parameters in the message
    params = parse_command_parameters(command.content)

    multiple_options = False
    only_numbers = False
    new_options = False

    poll_params = []

    # Filter the available options for polls
    for i in range(len(params)):
        if i == 0:
            continue
        elif params[i] == '-m':
            multiple_options = True
        elif params[i] == '-o':
            only_numbers = True
        elif params[i] == '-n':
            new_options = True
        else:
            # Add all non configuration parameters, ignoring quotation marks
            poll_params.append(params[i].replace('"', ''))

    # If the command has an invalid number of parameters
    if len(poll_params) < 2:
        msg = 'Invalid parameters in command: **%s**' % command.content

        await send_temp_message(msg, command.channel)
        return

    poll_id = poll_params[0]

    # Select the current poll
    poll = session.query(Poll).filter(Poll.poll_id == poll_id).first()

    # If no poll was found with that id
    if poll is None:
        msg = 'There\'s no poll with that id for you to edit.\nYour command: **%s**' % command.content

        await send_temp_message(msg, command.channel)
        return

    # Only the author can edit
    if poll.author != command.author.mention:
        msg = 'Only the author of a poll can edit it!'

        await send_temp_message(msg, command.channel)
        return

    poll.question = poll_params[1]
    poll.multiple_options = multiple_options
    poll.only_numbers = only_numbers
    poll.new_options = new_options

    msg_options = poll_params[2:]

    # Get all options available in the poll
    options = session.query(Option).filter(Option.poll_id == poll.id).all()

    # Update the options
    if len(msg_options) == len(options):
        for i in range(len(options)):
            options[i].option = msg_options[i]

    # Edit message
    c = client.get_channel(db_channel.discord_id)

    try:
        m = await client.get_message(c, poll.message_id)

        await client.edit_message(m, create_message(poll, options))
    except discord.errors.NotFound:
        session.delete(poll)

    session.commit()


async def close_poll_command(command, db_channel):
    """
    Close a poll.

    :param command: the command used.
    :param db_channel: the corresponding channel entry in the DB.
    """

    # If the channel does not exist in the DB
    if db_channel is None:
        msg = 'There\'s no poll in this channel for you to close!'

        await send_temp_message(msg, command.channel)
        return

    # Get the list of parameters in the message
    params = parse_command_parameters(command.content)

    # If the command has an invalid number of parameters
    if len(params) != 3:
        msg = 'Invalid parameters in command: **%s**' % command.content

        await send_temp_message(msg, command.channel)
        return

    poll_id = params[1]

    # Split the selected options
    list_options = params[2].split(',')

    # Options are all numbers
    try:
        # Verify if the options are numbers
        selected_options = []

        for o in list_options:
            selected_options.append(int(o))

        # Select the current poll
        poll = session.query(Poll).filter(Poll.poll_id == poll_id).first()

        # Edit the message with the poll
        if poll is not None:
            # Only the author can close the poll
            if poll.author == command.author.mention:
                options = session.query(Option).filter(Option.poll_id == poll.id).all()

                await close_poll(poll, db_channel, options, selected_options)

                session.commit()
        else:
            msg = 'There\'s no poll with that id for you to close.\nYour command: **%s**' % command.content

            await send_temp_message(msg, command.channel)
    except ValueError:
        pass


async def remove_poll(command, db_channel):
    """
    Remove a poll.

    :param command: the command used.
    :param db_channel: the corresponding channel entry in the DB.
    """

    # If the channel does not exist in the DB
    if db_channel is None:
        msg = 'There\'s no poll in this channel for you to remove!'

        await send_temp_message(msg, command.channel)
        return

    # Get the list of parameters in the message
    params = parse_command_parameters(command.content)

    # If the command has an invalid number of parameters
    if len(params) != 2:
        msg = 'Invalid parameters in command: **%s**' % command.content

        await send_temp_message(msg, command.channel)
        return

    poll_id = params[1]

    # Select the current poll
    poll = session.query(Poll).filter(Poll.poll_id == poll_id).first()

    # Delete the message with the poll
    if poll is not None:
        # Only the author can remove the poll
        if poll.author == command.author.mention:
            c = client.get_channel(db_channel.discord_id)

            try:
                m = await client.get_message(c, poll.message_id)

                await client.delete_message(m)
            except discord.errors.NotFound:
                pass

            session.delete(poll)
    else:
        msg = 'There\'s no poll with that id for you to close.\nYour command: **%s**' % command.content

        await send_temp_message(msg, command.channel)

    session.commit()


async def vote_poll(command, db_channel):
    """
    Vote a list of options in a poll.

    :param command: the command used.
    :param db_channel: the corresponding channel entry in the DB.
    """

    # If the channel does not exist in the DB
    if db_channel is None:
        msg = 'There\'s no poll in this channel for you to vote!'

        await send_temp_message(msg, command.channel)
        return

    # Get the list of parameters in the message
    params = parse_command_parameters(command.content)

    # If the command has an invalid number of parameters
    if len(params) != 3:
        msg = 'Invalid parameters in command: **%s**' % command.content

        await send_temp_message(msg, command.channel)
        return

    poll_id = params[1]
    option = params[2]

    # Select the current poll
    poll = session.query(Poll).filter(Poll.poll_id == poll_id).first()

    # If no poll was found with that id
    if poll is None:
        msg = 'There\'s no poll with that id for you to vote.\nYour command: **%s**' % command.content

        await send_temp_message(msg, command.channel)
        return

    # Get all options available in the poll
    options = session.query(Option).filter(Option.poll_id == poll.id).all()

    poll_edited = False

    # Option is a number
    try:
        # Verify if the options are numbers
        selected_options = []

        for o in option.split(','):
            selected_options.append(int(o))

        for option in selected_options:
            # If it is a valid option
            if 0 < option <= len(poll.options):
                vote = session.query(Vote)\
                    .filter(Vote.option_id == options[option - 1].id)\
                    .filter(Vote.participant_id == command.author.mention).first()

                # Vote for an option if multiple options are allowed and he is yet to vote this option
                if poll.multiple_options and vote is None:
                    # Add the new vote
                    vote = Vote(options[option - 1].id, command.author.mention)
                    session.add(vote)

                    poll_edited = True

                # If multiple options are not allowed
                elif not poll.multiple_options:
                    # The participant didn't vote this option
                    if vote is None:
                        remove_prev_vote(options, command.author.mention)

                        # Add the new vote
                        vote = Vote(options[option - 1].id, command.author.mention)
                        session.add(vote)

                        poll_edited = True

    # Option is not a number
    except ValueError:
        if poll.new_options:
            if not poll.multiple_options:
                remove_prev_vote(options, command.author.mention)

            if option[0] == '"' and option[-1] == '"':
                # Remove quotation marks
                option = option.replace('"', '')

                # Add the new option to the poll
                option = Option(poll.id, option)
                options.append(option)
                session.add(option)

                session.flush()

                vote = Vote(option.id, command.author.mention)
                session.add(vote)

                poll_edited = True

    # Edit the message
    if poll_edited:
        c = client.get_channel(db_channel.discord_id)
        try:
            m = await client.get_message(c, poll.message_id)
            await client.edit_message(m, create_message(poll, options))
        except discord.errors.NotFound:
            session.delete(poll)

    session.commit()


async def remove_vote(command, db_channel):
    """
    Remove a vote from an option in a poll.

    :param command: the command used.
    :param db_channel: the corresponding channel entry in the DB.
    """

    # If the channel does not exist in the DB
    if db_channel is None:
        msg = 'There\'s no poll in this channel for you to unvote!'

        await send_temp_message(msg, command.channel)
        return

    # Get the list of parameters in the message
    params = parse_command_parameters(command.content)

    # If the command has an invalid number of parameters
    if len(params) != 3:
        msg = 'Invalid parameters in command: **%s**' % command.content

        await send_temp_message(msg, command.channel)
        return

    poll_id = params[1]
    option = params[2]

    # Select the current poll
    poll = session.query(Poll).filter(Poll.poll_id == poll_id).first()

    # If no poll was found with that id
    if poll is None:
        msg = 'There\'s no poll with that id for you to remove.\nYour command: **%s**' % command.content

        await send_temp_message(msg, command.channel)
        return

    # Get all options available in the poll
    options = session.query(Option).filter(Option.poll_id == poll.id).all()

    # Option is a number
    try:
        option = int(option)

        # If it is a valid option
        if 0 < option <= len(poll.options):
            vote = session.query(Vote)\
                .filter(Vote.option_id == options[option - 1].id)\
                .filter(Vote.participant_id == command.author.mention).first()

            if vote is not None:
                # Remove the vote from this option
                session.delete(vote)

                # Edit the message
                c = client.get_channel(db_channel.discord_id)

                try:
                    m = await client.get_message(c, poll.message_id)

                    await client.edit_message(m, create_message(poll, options))
                except discord.errors.NotFound:
                    session.delete(poll)

                session.commit()

    # Option is not a number
    except ValueError:
        pass


async def refresh_poll(command, db_channel):
    """
    Show a pole in a new message.

    :param command: the command used.
    :param db_channel: the corresponding channel entry in the DB.
    """

    # If the channel does not exist in the DB
    if db_channel is None:
        msg = 'There\'s no poll in this channel for you to refresh!'

        await send_temp_message(msg, command.channel)
        return

    # Get the list of parameters in the message
    params = parse_command_parameters(command.content)

    # If the command has an invalid number of parameters
    if len(params) != 2:
        msg = 'Invalid parameters in command: **%s**' % command.content

        await send_temp_message(msg, command.channel)
        return

    poll_id = params[1]

    # Select the current poll
    poll = session.query(Poll).filter(Poll.poll_id == poll_id).first()

    # Create the message with the poll
    if poll is not None:
        options = session.query(Option).filter(Option.poll_id == poll.id).all()

        msg = await client.send_message(command.channel, create_message(poll, options))
        poll.message_id = msg.id

        session.commit()


async def help_message(command, db_channel):
    """
    Show a help message with the available commands.

    :param command: the command used.
    :param db_channel: the corresponding channel entry in the DB.
    """

    # The id of the Discord channel where the message was sent
    channel_id = command.channel.id

    # Create channel if it doesn't already exist
    if db_channel is None:
        db_channel = Channel(channel_id)

        session.add(db_channel)
        session.commit()

    msg = 'Poll Me Bot Help\n' \
          '----------------\n' \
          'For creating a poll: *!poll poll_id "Question" "Option 1" "Option 2"*\n' \
          'For voting for an option: *!vote poll_id list_of_numbers_separated_by_comma*\n' \
          'For removing your vote for that option: *!unvote poll_id number*\n' \
          '(More options and details are available at https://github.com/correia55/PollMeBot)\n' \
          '(This message will self-destruct in 30 seconds.)'

    await send_temp_message(msg, command.channel)


# endregion


# region Auxiliary Functions

def parse_command_parameters(command):
    """
    Parse the command, separating commands by spaces, ignoring spaces within quotation marks.

    :param command: the unparsed command.
    :return: the list of parameters.
    """

    rem_qm = command.split('"')

    params = []

    for i in range(len(rem_qm)):
        if rem_qm[i] == '':
            continue

        # If it's even
        if i % 2 == 0:
            for p in rem_qm[i].split(' '):
                if p != '':
                    params.append(p)
        # If it's odd
        else:
            params.append('"%s"' % rem_qm[i])

    return params


def create_message(poll, options, selected_options=None):
    """
    Creates a message given a poll.

    :param poll: the poll.
    :param options: the options available in the poll.
    :param selected_options: the list of options that are to be displayed in the closed poll.
    :return: the message that represents the poll.
    """

    if selected_options is not None:
        msg = '**%s** (Closed)' % poll.question
    else:
        msg = '**%s** (poll_id: %s)' % (poll.question, poll.poll_id)

    for i in range(len(options)):
        # Ignore the options not selected
        if selected_options is not None:
            if i + 1 not in selected_options:
                continue

        msg += '\n%d - %s' % ((i + 1), options[i].option)

        # Get all votes for that option
        votes = session.query(Vote).filter(Vote.option_id == options[i].id).all()

        if len(votes) > 0:
            msg += ':'

            # Show the number of voters for the option
            if poll.only_numbers:
                msg += ' %d vote.' % len(votes)
            # Show the names of the voters for the option
            else:
                for v in votes:
                    msg += ' %s' % v.participant_id

    if selected_options is None:
        if poll.new_options:
            msg += '\n(New options can be suggested!)'

        if poll.multiple_options:
            msg += '\n(You can vote on multiple options!)'

    return msg


def remove_prev_vote(options, participant):
    """
    Remove the previous vote of a participant.

    :param options: the options available in the poll.
    :param participant: the id of the participant whose vote is to remove.
    """

    ids = []

    for o in options:
        ids.append(o.id)

    # Get the previous vote
    prev_vote = session.query(Vote).filter(Vote.option_id.in_(ids)).filter(Vote.participant_id == participant).first()

    # If it had voted for something else remove it
    if prev_vote is not None:
        session.delete(prev_vote)


async def close_poll(poll, db_channel, options, selected_options):
    """
    Delete a poll from the DB and update the message to closed poll.

    :param poll: the poll to close.
    :param db_channel: the corresponding channel entry in the DB.
    :param options: the list of options available in the poll.
    :param selected_options: the list of options that are to be displayed in the closed poll.
    """

    # Edit the message to display as closed
    c = client.get_channel(db_channel.discord_id)

    try:
        m = await client.get_message(c, poll.message_id)

        await client.edit_message(m, create_message(poll, options, selected_options=selected_options))
    except discord.errors.NotFound:
        pass

    # Delete the poll from the DB
    session.delete(poll)
    session.flush()


async def check_messages_exist():
    """
    Check all messages and channels to see if they still exist.

    :return:
    """

    while True:
        channels = session.query(Channel).all()

        # Delete all channels that no longer exist
        for channel in channels:
            c = client.get_channel(channel.discord_id)

            if c is None:
                session.delete(channel)

        session.flush()

        polls = session.query(Poll).all()

        # Delete all polls that no longer exist
        for poll in polls:
            channel = session.query(Channel).filter(Channel.id == poll.channel_id).first()

            c = client.get_channel(channel.discord_id)

            try:
                await client.get_message(c, poll.message_id)
            except discord.errors.NotFound:
                session.delete(poll)

        session.commit()

        print('Checking for deleted messages and channels...Done')

        await asyncio.sleep(CHECK_DELETED_WAIT_TIME)


async def send_temp_message(message, channel, time=30):
    """
    Show a temporary message.

    :param message: the message sent.
    :param channel: the Discord channel.
    :param time: the time before deleting the temporary message.
    """

    # Send the message
    msg = await client.send_message(channel, message)

    # Wait for 30 seconds
    await asyncio.sleep(time)

    # Delete this message
    try:
        await client.delete_message(msg)
    except discord.errors.NotFound:
        pass


# endregion


# Run the bot
client.run(token)
