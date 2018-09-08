import os
import shlex
import discord
import asyncio

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy import Column, String, Integer, Boolean, ForeignKey

engine = create_engine('postgresql://acorreia:1234@localhost:5432/poll-me-bot')
Session = sessionmaker(bind=engine)

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

    options = relationship('Option', cascade='all,delete')

    def __init__(self, poll_id, author, question, multiple_options, only_numbers, new_options, channel_id):
        self.poll_id = poll_id
        self.author = author
        self.question = question
        self.multiple_options = multiple_options
        self.only_numbers = only_numbers
        self.new_options = new_options
        self.channel_id = channel_id


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


# region Events

# When the bot has started
@client.event
async def on_ready():
    print('The bot is ready to poll!\n-------------------------')


# When a message is written in Discord
@client.event
async def on_message(message):
    # Get the channel information from the DB
    channel = session.query(Channel).filter(Channel.discord_id == message.channel.id).first()

    # Configure the channel
    if message.content.startswith('!poll_me_channel'):
        await configure_channel(message)
    # Edit a poll
    elif message.content.startswith('!poll_edit'):
        if channel is not None:
            await edit_poll(message, channel)
    # Remove a poll
    elif message.content.startswith('!poll_remove '):
        if channel is not None:
            await remove_poll(message, channel)
    # Start a new poll
    elif message.content.startswith('!poll'):
        await create_poll(message)
    # Vote in a poll
    elif message.content.startswith('!vote '):  # Extra space is necessary
        if channel is not None:
            await vote_poll(message, channel)
    # Remove a vote from a poll
    elif message.content.startswith('!unvote'):
        if channel is not None:
            await remove_vote(message, channel)
    # Show the current poll in a new message
    elif message.content.startswith('!refresh '):  # Extra space is necessary
        if channel is not None:
            await refresh_poll(message, channel)
    # Show a help me message
    elif message.content.startswith('!help_me_poll'):
        await help_message(message)

    # Delete all messages
    if channel is not None:
        if channel.delete_all and message.author.mention != client.user:
            await client.delete_message(message)


# endregion

# region Commands

# Configure the channel
async def configure_channel(message):
    channel_id = message.channel.id
    comps = message.content.split(' ')

    channel = session.query(Channel).filter(Channel.discord_id == channel_id).first()

    if len(comps) != 2:
        if channel is not None:
            # Delete the message that contains this command
            if channel.delete_commands:
                await client.delete_message(message)

        return

    delete_commands = False
    delete_all = False

    if comps[1] == '-dc':
        delete_commands = True
    elif comps[1] == '-da':
        delete_all = True
    elif comps[1] == '-ka':
        delete_commands = False
        delete_all = False

    # Create or modify the channel with the correct configurations
    if channel is None:
        channel = Channel(channel_id, delete_commands, delete_all)

        session.add(channel)
    else:
        channel.delete_commands = delete_commands
        channel.delete_all = delete_all

    session.commit()

    # Delete the message that contains this command
    if channel.delete_commands:
        await client.delete_message(message)


# Create a new poll
async def create_poll(message):
    channel_id = message.channel.id

    channel = session.query(Channel).filter(Channel.discord_id == channel_id).first()

    # Create channel if it doesn't already exist
    if channel is None:
        channel = Channel(channel_id)
        session.add(channel)

    # Split the command using spaces, ignoring those between quotation marks
    comps = shlex.split(message.content)[1:]

    multiple_options = False
    only_numbers = False
    new_options = False

    poll_comps = []

    # Filter the available options for polls
    for i in range(len(comps)):
        if comps[i] == '-m':
            multiple_options = True
        elif comps[i] == '-o':
            only_numbers = True
        elif comps[i] == '-n':
            new_options = True
        else:
            poll_comps.append(comps[i])

    if len(poll_comps) < 2:
        return

    # Create the new poll
    new_poll = Poll(poll_comps[0], message.author.mention, poll_comps[1], multiple_options, only_numbers, new_options,
                    channel.id)

    session.add(new_poll)

    # Necessary for the options to get the poll id
    session.flush()

    options = []

    # Create the options
    for option in poll_comps[2:]:
        options.append(Option(new_poll.id, option))

    session.add_all(options)

    # Limit the number of polls to 5 per channel
    if session.query(Poll).filter(Poll.channel_id == channel.id).count() == 5:
        poll = session.query(Poll).first()

        session.delete(poll)

    # Create the message with the poll
    msg = await client.send_message(message.channel, create_message(new_poll, options))

    new_poll.message_id = msg.id

    session.commit()

    # Delete the message that contains this command
    if channel.delete_commands:
        await client.delete_message(message)


# Edit a poll
async def edit_poll(message, channel):
    # Split the command using spaces, ignoring those between quotation marks
    comps = shlex.split(message.content)[1:]

    multiple_options = False
    only_numbers = False
    new_options = False

    poll_comps = []

    # Filter the available options for polls
    for i in range(len(comps)):
        if comps[i] == '-m':
            multiple_options = True
        elif comps[i] == '-o':
            only_numbers = True
        elif comps[i] == '-n':
            new_options = True
        else:
            poll_comps.append(comps[i])

    if len(poll_comps) < 2:
        return

    poll_id = poll_comps[0]

    # Select the current poll
    poll = session.query(Poll).filter(Poll.poll_id == poll_id).first()

    # If no poll was found with that id
    if poll is None:
        # Delete the message that contains this command
        if channel.delete_commands:
            await client.delete_message(message)

        return

    # Only the author can edit
    if poll.author != message.author.mention:
        # Delete the message that contains this command
        if channel.delete_commands:
            await client.delete_message(message)

        return

    poll.question = poll_comps[1]
    msg_options = poll_comps[2:]

    options = session.query(Option).filter(Option.poll_id == poll.id).all()

    # Update the options
    if len(msg_options) == len(options):
        for i in range(len(options)):
            options[i].option = msg_options[i]

    poll.multiple_options = multiple_options
    poll.only_numbers = only_numbers
    poll.new_options = new_options

    # Edit message
    c = client.get_channel(channel.discord_id)
    m = await client.get_message(c, poll.message_id)
    await client.edit_message(m, create_message(poll, options))

    session.commit()

    # Delete the message that contains this command
    if channel.delete_commands:
        await client.delete_message(message)


# Remove a poll
async def remove_poll(message, channel):
    poll_id = message.content.replace('!poll_remove ', '')

    # Select the current poll
    poll = session.query(Poll).filter(Poll.poll_id == poll_id).first()

    # Delete the message with the poll
    if poll is not None:
        # Only the author can remove the poll
        if poll.author == message.author.mention:
            c = client.get_channel(channel.discord_id)
            m = await client.get_message(c, poll.message_id)

            await client.delete_message(m)
            session.delete(poll)

    session.commit()

    # Delete the message that contains this command
    if channel.delete_commands:
        await client.delete_message(message)


# Vote in a poll
async def vote_poll(message, channel):
    # Split the command using spaces, ignoring those between quotation marks
    option = message.content.replace('!vote ', '')

    space_pos = option.find(' ')

    # There is no space
    if space_pos == -1:
        return

    poll_id = option[0:space_pos]
    option = option[space_pos + 1:]

    # Select the correct poll
    poll = session.query(Poll).filter(Poll.poll_id == poll_id).first()

    # If no poll was found with that id
    if poll is None:
        return

    # If the option is empty
    if len(option) == 0:
        if channel.delete_commands:
            await client.delete_message(message)

        return

    options = session.query(Option).filter(Option.poll_id == poll.id).all()

    # Option is a number
    try:
        option = int(option)

        # If it is a valid option
        if 0 < option <= len(poll.options):
            vote = session.query(Vote)\
                .filter(Vote.option_id == options[option - 1].id)\
                .filter(Vote.participant_id == message.author.mention).first()

            # Vote for an option if multiple options are allowed and he is yet to vote this option
            if poll.multiple_options and vote is None:
                # Add the new vote
                vote = Vote(options[option - 1].id, message.author.mention)
                session.add(vote)

                # Edit the message
                c = client.get_channel(channel.discord_id)
                m = await client.get_message(c, poll.message_id)
                await client.edit_message(m, create_message(poll, options))

            # If multiple options are not allowed
            elif not poll.multiple_options:
                # The participant didn't vote this option
                if vote is None:
                    remove_prev_vote(options, message.author.mention)

                    # Add the new vote
                    vote = Vote(options[option - 1].id, message.author.mention)
                    session.add(vote)

                    # Edit the message
                    c = client.get_channel(channel.discord_id)
                    m = await client.get_message(c, poll.message_id)
                    await client.edit_message(m, create_message(poll, options))

    # Option is not a number
    except ValueError:
        if poll.new_options:
            if not poll.multiple_options:
                remove_prev_vote(options, message.author.mention)

            if option[0] == '"' and option[-1] == '"':
                # Remove quotation marks
                option = option.replace('"', '')

                # Add the new option to the poll
                option = Option(poll.id, option)
                options.append(option)
                session.add(option)

                session.flush()

                vote = Vote(option.id, message.author.mention)
                session.add(vote)

                # Edit the message
                c = client.get_channel(channel.discord_id)
                m = await client.get_message(c, poll.message_id)
                await client.edit_message(m, create_message(poll, options))

    session.commit()

    # Delete the message that contains this command
    if channel.delete_commands:
        await client.delete_message(message)


# Remove a vote from a pole
async def remove_vote(message, channel):
    channel = channel_list[message.channel.id]

    # Split the command using spaces
    option = message.content.split(' ')

    if len(option) != 3:
        if channel.delete_commands:
            await client.delete_message(message)

        return

    poll_id = option[1]
    option = option[2]

    # Select the current poll for that channel
    poll, poll_pos = get_poll(channel, poll_id)

    if poll is None:
        # Delete the message that contains this command
        if channel.delete_commands:
            await client.delete_message(message)

        return

    # Option is a number
    try:
        option = int(option)

        # If it is a valid option
        if 0 < option <= len(poll.options):
            if message.author.mention in poll.participants[option - 1]:
                # Remove the vote from this option
                poll.participants[option - 1].remove(message.author.mention)
                await client.edit_message(poll.message_id, create_message(poll))

                # Save data to file
                save_data()

    # Option is not a number
    except ValueError:
        pass

    # Delete the message that contains this command
    if channel.delete_commands:
        await client.delete_message(message)


# Show a pole in a new message
async def refresh_poll(message, channel):
    channel = channel_list[message.channel.id]

    poll_id = message.content.replace('!refresh ', '')

    # Select the current poll for that channel
    poll, poll_pos = get_poll(channel, poll_id)

    # Create the message with the poll
    if poll is not None:
        poll.message_id = await client.send_message(message.channel, create_message(poll))

        # Save data to file
        save_data()

    # Delete the message that contains this command
    if channel.delete_commands:
        await client.delete_message(message)


# Show a help message with the available commands
async def help_message(message):
    channel_id = message.channel.id

    # Create channel if it doesn't already exist
    if channel_id not in channel_list:
        channel_list[channel_id] = Channel()

    channel = channel_list[channel_id]

    msg = 'Poll Me Bot Help\n' \
          '----------------\n' \
          'For creating a poll: *!poll poll_id "Question" "Option 1" "Option 2"*\n' \
          'For voting for an option: *!vote poll_id number*\n' \
          'For removing your vote for that option: *!unvote poll_id number*\n' \
          '(More options and details are available at https://github.com/correia55/PollMeBot)\n' \
          '(This message will self-destruct in 30 seconds.)'

    # Create the message with the help
    message_id = await client.send_message(message.channel, msg)

    # Delete the message that contains this command
    if channel.delete_commands:
        await client.delete_message(message)

    # Wait for 30 seconds
    await asyncio.sleep(30)

    # Delete this message
    await client.delete_message(message_id)


# endregion

# region Auxiliary Functions

# Creates a message given a poll
def create_message(poll, options):
    msg = '**%s** (poll_id: %s)' % (poll.question, poll.poll_id)

    for i in range(len(options)):
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

    if poll.new_options:
        msg += '\n(New options can be suggested!)'

    if poll.multiple_options:
        msg += '\n(You can vote on multiple options!)'

    return msg


# Remove the previous vote of a participant
def remove_prev_vote(options, participant):
    ids = []

    for o in options:
        ids.append(o.id)

    # Get the previous vote
    prev_vote = session.query(Vote).filter(Vote.option_id.in_(ids)).filter(Vote.participant_id == participant).first()

    # If it had voted for something else remove it
    if prev_vote is not None:
        session.delete(prev_vote)


# endregion


# Run the bot
client.run(token)
