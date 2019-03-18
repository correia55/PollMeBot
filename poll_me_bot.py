import os
import discord
import asyncio
import datetime

import alembic.config as aleconf
import alembic.command as alecomm
import alembic.migration as alemig
import alembic.autogenerate as aleauto

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models

# Names of weekdays in English and Portuguese
WEEKDAYS_EN = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
WEEKDAYS_PT = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']

# region Initialization
database_url = os.environ.get('DATABASE_URL', None)

if database_url is None:
    print('Unable to find database url!')
    exit(1)

engine = create_engine(database_url)
Session = sessionmaker(bind=engine)

MIGRATIONS_DIR = './migrations/'

config = aleconf.Config(file_='%salembic.ini' % MIGRATIONS_DIR)
config.set_main_option('script_location', MIGRATIONS_DIR)
config.set_main_option('sqlalchemy.url', database_url)

# Create tables if they don't exist
if not os.path.isdir(MIGRATIONS_DIR):
    alecomm.init(config, MIGRATIONS_DIR)

    env_file = open('%senv.py' % MIGRATIONS_DIR, 'r+')
    text = env_file.read()
    text = text.replace('target_metadata=target_metadata', 'target_metadata=target_metadata, compare_type=True')
    text = text.replace('target_metadata = None', 'import models\ntarget_metadata = models.base.metadata')
    env_file.seek(0)
    env_file.write(text)
    env_file.close()

# Makes sure the database is up to date
alecomm.upgrade(config, 'head')

# Check for changes in the database
mc = alemig.MigrationContext.configure(engine.connect())
diff_list = aleauto.compare_metadata(mc, models.base.metadata)

# Update the database
if diff_list:
    alecomm.revision(config, None, autogenerate=True)
    alecomm.upgrade(config, 'head')

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
    db_channel = session.query(models.Channel).filter(models.Channel.discord_id == message.channel.id).first()

    is_command = True

    # Check if it is a command and call the correct function to treat it
    if message.content.startswith('!poll_channel '):
        await configure_channel(message, db_channel)
    elif message.content.startswith('!poll_edit '):
        await edit_poll(message, db_channel)
    elif message.content.startswith('!poll_close '):
        await close_poll_command(message, db_channel)
    elif message.content.startswith('!poll_remove '):
        await remove_poll(message, db_channel)
    elif message.content.startswith('!poll_refresh '):
        await refresh_poll(message, db_channel)
    elif message.content.startswith('!poll '):
        await create_poll(message, db_channel)
    elif message.content.startswith('!vote '):
        await vote_poll(message, db_channel)
    elif message.content.startswith('!unvote '):
        await unvote_poll(message, db_channel)
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


# When a reaction is added in Discord
@client.event
async def on_reaction_add(reaction, user):
    if user == client.user:
        return

    # Select the current poll
    poll = session.query(models.Poll).filter(models.Poll.message_id == reaction.message.id).first()

    # The reaction was to a message that is not a poll
    if poll is None:
        return

    # Get the number of the vote
    option = ord(reaction.emoji[0]) - 48

    if option > 9:
        return

    # Get all options available in the poll
    db_options = session.query(models.Option).filter(models.Option.poll_id == poll.id).order_by(models.Option.position).all()

    # Get the channel information from the DB
    db_channel = session.query(models.Channel).filter(models.Channel.discord_id == reaction.message.channel.id).first()

    poll_edited = add_vote(option, user.id, user.mention, db_options, poll.multiple_options)

    # Edit the message
    if poll_edited:
        c = client.get_channel(db_channel.discord_id)

        try:
            m = await client.get_message(c, poll.message_id)
            await client.edit_message(m, create_message(reaction.message.server, poll, db_options))
        except discord.errors.NotFound:
            session.delete(poll)

    session.commit()


# When a reaction is removed in Discord
@client.event
async def on_reaction_remove(reaction, user):
    if user == client.user:
        return

    # Select the current poll
    poll = session.query(models.Poll).filter(models.Poll.message_id == reaction.message.id).first()

    # The reaction was to a message that is not a poll
    if poll is None:
        return

    # Get the number of the vote
    option = ord(reaction.emoji[0]) - 48

    if option > 9:
        return

    # Get all options available in the poll
    db_options = session.query(models.Option).filter(models.Option.poll_id == poll.id).order_by(models.Option.position).all()

    # Get the channel information from the DB
    db_channel = session.query(models.Channel).filter(models.Channel.discord_id == reaction.message.channel.id).first()

    poll_edited = remove_vote(option, user.mention, db_options)

    # Edit the message
    if poll_edited:
        c = client.get_channel(db_channel.discord_id)

        try:
            m = await client.get_message(c, poll.message_id)
            await client.edit_message(m, create_message(reaction.message.server, poll, db_options))
        except discord.errors.NotFound:
            session.delete(poll)

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
        db_channel = models.Channel(channel_id, delete_commands, delete_all)

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
        db_channel = models.Channel(channel_id)

        session.add(db_channel)

    # Get the list of parameters in the message
    params = parse_command_parameters(command.content)

    weekly = False
    pt = False
    day_param_pos = -1
    day_param_poll_pos = -1

    multiple_options = False
    only_numbers = False
    new_options = False
    allow_external = False

    # Confirmation is necessary when there is a need to close a poll before this one is created
    confirmation = False

    poll_params = []

    # Filter the available configurations for polls
    for i in range(len(params)):
        if i == 0:
            continue

        if params[i] == '-weekly':
            weekly = True
            pt = False
            day_param_pos = i + 1
            day_param_poll_pos = len(poll_params)
        elif params[i] == '-weekly_pt':
            weekly = True
            pt = True
            day_param_pos = i + 1
            day_param_poll_pos = len(poll_params)
        elif params[i].startswith('-'):
            if params[i].__contains__('m'):
                multiple_options = True
            if params[i].__contains__('o'):
                only_numbers = True
            if params[i].__contains__('n'):
                new_options = True
            if params[i].__contains__('e'):
                allow_external = True
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
    poll = session.query(models.Poll).filter(models.Poll.poll_id == poll_params[0]).first()

    # If a poll with the same id already exists, close it
    if poll is not None:
        # Confirmation required before closing a poll
        if not confirmation:
            msg = 'A poll with that id already exists add **-y** to your command to confirm the closing of the ' \
                  'previous poll.\nYour command: **%s**' % command.content

            await send_temp_message(msg, command.channel)
            return

        # Get all options available in the poll
        options = session.query(models.Option).filter(models.Option.poll_id == poll.id).order_by(models.Option.position).all()

        await close_poll(poll, db_channel, options, range(1, len(options) + 1))

    # Limit the number of polls per server
    while session.query(models.Poll).filter(models.Poll.server_id == server_id).count() >= POLL_LIMIT_SERVER:
        # Confirmation required before closing other polls
        if not confirmation:
            msg = 'The server you\'re in has reached its poll limit, creating another poll will force the closing of ' \
                  'the oldest poll still active. Add **-y** to your command to confirm the closing of the ' \
                  'previous poll.\nYour command: **%s**' % command.content

            await send_temp_message(msg, command.channel)
            return

        poll = session.query(models.Poll).filter(models.Poll.server_id == server_id).first()

        # Get all options available in the poll
        options = session.query(models.Option).filter(models.Option.poll_id == poll.id).order_by(models.Option.position).all()

        await close_poll(poll, db_channel, options, range(1, len(options) + 1))

    # Create the new poll
    new_poll = models.Poll(poll_params[0], command.author.id, poll_params[1], multiple_options, only_numbers, new_options,
                    allow_external, db_channel.id, server_id)

    session.add(new_poll)

    # Send a private message to each member in the server
    for m in command.server.members:
        if m != client.user and m.id != new_poll.author:
            try:
                await client.send_message(m, 'A new poll (%s) has been created in %s!'
                                          % (new_poll.poll_id, command.channel.mention))
            except discord.errors.Forbidden:
                pass

    # Necessary for the options to get the poll id
    session.flush()

    options = []

    # Get the current dates
    start_date = datetime.datetime.today()

    num_options = max(6 - start_date.weekday(), 0)
    end_date = start_date + datetime.timedelta(days=num_options)

    # Calculate the date interval for the options
    if weekly and day_param_poll_pos < len(poll_params):
        try:
            days = params[day_param_pos].split(',')

            starting_day = int(days[0])
            start_date = date_given_day(start_date, starting_day)

            if len(days) > 1:
                end_day = int(days[1])
                end_date = date_given_day(start_date, end_day)
            else:
                num_options = max(6 - start_date.weekday(), 0)
                end_date = start_date + datetime.timedelta(days=num_options)

            # Remove this option
            poll_params.remove(poll_params[day_param_poll_pos])
        except ValueError:
            pass

    # Create the options
    if len(poll_params[2:]) != 0 or weekly:
        # Add days of the week as options
        if weekly:
            while start_date <= end_date:
                # Name depending on the option used
                if pt:
                    day_name = WEEKDAYS_PT[start_date.weekday()]
                else:
                    day_name = WEEKDAYS_EN[start_date.weekday()]

                options.append(models.Option(new_poll.id, len(options) + 1, '%s (%s)' % (day_name, start_date.day)))
                start_date = start_date + datetime.timedelta(days=1)

        for option in poll_params[2:]:
            options.append(models.Option(new_poll.id, len(options) + 1, option))

    # If no options were provided, then create the default Yes and No
    else:
        options.append(models.Option(new_poll.id, 1, 'Yes'))
        options.append(models.Option(new_poll.id, 2, 'No'))

    session.add_all(options)

    # Create the message with the poll
    msg = await client.send_message(command.channel, create_message(command.server, new_poll, options))

    new_poll.message_id = msg.id

    # Add a reaction for each option, with 9 being the max number of reactions
    emoji = u'\u0031'

    for i in range(min(len(options), 9)):
        await client.add_reaction(msg, emoji + u'\u20E3')
        emoji = chr(ord(emoji) + 1)

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

    add = False
    remove = False
    lock = False
    unlock = False

    multiple_options = False
    only_numbers = False
    new_options = False
    allow_external = False

    poll_params = []

    # Filter the available options for polls
    for i in range(len(params)):
        if i == 0:
            continue

        if params[i] == '-add':
            add = True
            remove = False
            lock = False
            unlock = False
        elif params[i] == '-rm':
            remove = True
            add = False
            lock = False
            unlock = False
        elif params[i] == '-lock':
            remove = False
            add = False
            lock = True
            unlock = False
        elif params[i] == '-unlock':
            remove = False
            add = False
            lock = False
            unlock = True
        elif params[i].startswith('-'):
            if params[i].__contains__('m'):
                multiple_options = True
            if params[i].__contains__('o'):
                only_numbers = True
            if params[i].__contains__('n'):
                new_options = True
            if params[i].__contains__('e'):
                allow_external = True
        else:
            # Add all non configuration parameters, ignoring quotation marks
            poll_params.append(params[i].replace('"', ''))

    # If the command has an invalid number of parameters
    if (len(poll_params) < 2 and (add or remove or lock or unlock)) or (len(poll_params) < 1 and not add and not remove and not lock and not unlock):
        msg = 'Invalid parameters in command: **%s**' % command.content

        await send_temp_message(msg, command.channel)
        return

    poll_id = poll_params[0]

    # Select the current poll
    poll = session.query(models.Poll).filter(models.Poll.poll_id == poll_id).first()

    # If no poll was found with that id
    if poll is None:
        msg = 'There\'s no poll with that id for you to edit.\nYour command: **%s**' % command.content

        await send_temp_message(msg, command.channel)
        return

    # Only the author can edit
    if poll.author != command.author.id:
        msg = 'Only the author of a poll can edit it!'

        await send_temp_message(msg, command.channel)
        return

    # Get all options available in the poll
    db_options = session.query(models.Option).filter(models.Option.poll_id == poll.id).order_by(models.Option.position).all()

    # Add the new options
    if add:
        new_options = poll_params[1:]

        options = []

        # Create the options
        for option in new_options:
            options.append(models.Option(poll.id, len(options) + 1, option))

        session.add_all(options)

        # Get the message corresponding to the poll
        c = client.get_channel(db_channel.discord_id)
        poll_msg = await client.get_message(c, poll.message_id)

        # Add a reaction for each new option
        emoji = chr(ord(u'\u0031') + len(db_options))

        # Max number of reactions that can be added
        num_react = min(9, len(db_options) + len(options))

        for i in range(max(0, num_react - len(db_options))):
            await client.add_reaction(poll_msg, emoji + u'\u20E3')
            emoji = chr(ord(emoji) + 1)

        db_options.extend(options)
    # Remove, lock or unlock options
    elif remove or lock or unlock:
        rm_options = poll_params[1]

        # Option is a number
        try:
            # Verify if the options are numbers
            selected_options = []

            for o in rm_options.split(','):
                selected_options.append(int(o))

            # Removes duplicates in the list
            selected_options = list(set(selected_options))

            # Sort list in decreasing order, preventing incorrect removal of options
            selected_options.sort(reverse=True)

            # Get the message corresponding to the poll
            c = client.get_channel(db_channel.discord_id)
            poll_msg = await client.get_message(c, poll.message_id)

            for option in selected_options:
                num_options = len(db_options)

                # If it is a valid option
                if 0 < option <= num_options:
                    if remove:
                        # Remove the option - needs to be before the removal of reactions or it causes problems
                        session.delete(db_options[option - 1])
                        db_options.remove(db_options[option - 1])

                        # Remove the reaction for the highest option
                        if num_options < 10:
                            emoji = chr(ord(u'\u0031') + num_options - 1)

                            users = None

                            # Get all users with that reaction
                            for reaction in poll_msg.reactions:
                                if reaction.emoji == (emoji + u'\u20E3'):
                                    users = await client.get_reaction_users(reaction)

                            if users is not None:
                                for user in users:
                                    await client.remove_reaction(poll_msg, emoji + u'\u20E3', user)

                            await client.remove_reaction(poll_msg, emoji + u'\u20E3', client.user)
                    elif lock:
                        db_options[option - 1].locked = True
                    elif unlock:
                        db_options[option - 1].locked = False

        # Option is not a number
        except ValueError:
            pass
    else:
        # Edit poll question
        if len(poll_params) > 1:
            poll.question = poll_params[1]
        # Edit poll settings
        else:
            poll.multiple_options = multiple_options
            poll.only_numbers = only_numbers
            poll.new_options = new_options
            poll.allow_external = allow_external

    # Edit message
    c = client.get_channel(db_channel.discord_id)

    try:
        m = await client.get_message(c, poll.message_id)

        await client.edit_message(m, create_message(command.server, poll, db_options))
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
        poll = session.query(models.Poll).filter(models.Poll.poll_id == poll_id).first()

        # Edit the message with the poll
        if poll is not None:
            # Only the author can close the poll
            if poll.author == command.author.id:
                options = session.query(models.Option).filter(models.Option.poll_id == poll.id).order_by(models.Option.position).all()

                # Send a private message to all participants in the poll
                await send_closed_poll_message(options, command.server, poll, command.channel)

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
    poll = session.query(models.Poll).filter(models.Poll.poll_id == poll_id).first()

    # Delete the message with the poll
    if poll is not None:
        # Only the author can remove the poll
        if poll.author == command.author.id:
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
    models.Vote a list of options in a poll.

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

    # Check for external voters
    if params.__contains__('-e') and len(params) == 5:
        author_id = None
        author_mention = params[4]

        if author_mention[0] != '"':
            author_mention = '"%s"' % author_mention
    else:
        # If the command has an invalid number of parameters
        if len(params) != 3:
            msg = 'Invalid parameters in command: **%s**' % command.content

            await send_temp_message(msg, command.channel)
            return

        author_id = command.author.id
        author_mention = command.author.mention

    poll_id = params[1]
    options = params[2]

    # Select the current poll
    poll = session.query(models.Poll).filter(models.Poll.poll_id == poll_id).first()

    # If no poll was found with that id
    if poll is None:
        msg = 'There\'s no poll with that id for you to vote.\nYour command: **%s**' % command.content

        await send_temp_message(msg, command.channel)
        return

    # Get all options available in the poll
    db_options = session.query(models.Option).filter(models.Option.poll_id == poll.id).order_by(models.Option.position).all()

    # If it is an vote for an external user and it is not allowed
    if author_id is None and not poll.allow_external:
        msg = 'models.Poll *%s* does not allow for external votes.\nIf you need this option, ask the poll author to edit it.' % poll_id

        await send_temp_message(msg, command.channel)
        return

    poll_edited = False

    # Option is a list of numbers
    try:
        # Verify if the options are numbers
        selected_options = []

        for o in options.split(','):
            selected_options.append(int(o))

        for option in selected_options:
            poll_edited |= add_vote(option, author_id, author_mention, db_options, poll.multiple_options)

    # Option is not a list of numbers
    except ValueError:
        if poll.new_options:
            if not poll.multiple_options:
                remove_prev_vote(db_options, author_mention)

            if options[0] == '"' and options[-1] == '"':
                # Remove quotation marks
                options = options.replace('"', '')

                # Add the new option to the poll
                options = models.Option(poll.id, len(db_options) + 1, options)
                db_options.append(options)
                session.add(options)

                session.flush()

                vote = models.Vote(options.id, author_id, author_mention)
                session.add(vote)

                poll_edited = True
        else:
            msg = 'models.Poll *%s* does not allow for new votes.\nIf you need this option, ask the poll author to edit it.' % poll_id

            await send_temp_message(msg, command.channel)
            return

    # Edit the message
    if poll_edited:
        c = client.get_channel(db_channel.discord_id)

        try:
            m = await client.get_message(c, poll.message_id)
            await client.edit_message(m, create_message(command.server, poll, db_options))
        except discord.errors.NotFound:
            session.delete(poll)

    session.commit()


async def unvote_poll(command, db_channel):
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

    # Check for external voters
    if params.__contains__('-e') and len(params) == 5:
        author_mention = params[4]

        if author_mention[0] != '"':
            author_mention = '"%s"' % author_mention
    else:
        # If the command has an invalid number of parameters
        if len(params) != 3:
            msg = 'Invalid parameters in command: **%s**' % command.content

            await send_temp_message(msg, command.channel)
            return

        author_mention = command.author.mention

    poll_id = params[1]
    options = params[2]

    # Select the current poll
    poll = session.query(models.Poll).filter(models.Poll.poll_id == poll_id).first()

    # If no poll was found with that id
    if poll is None:
        msg = 'There\'s no poll with that id for you to remove.\nYour command: **%s**' % command.content

        await send_temp_message(msg, command.channel)
        return

    # Get all options available in the poll
    db_options = session.query(models.Option).filter(models.Option.poll_id == poll.id).order_by(models.Option.position).all()

    poll_edited = False

    # Option is a number
    try:
        # Verify if the options are numbers
        selected_options = []

        for o in options.split(','):
            selected_options.append(int(o))

        for option in selected_options:
            poll_edited |= remove_vote(option, author_mention, db_options)

        if poll_edited:
            # Edit the message
            c = client.get_channel(db_channel.discord_id)

            try:
                m = await client.get_message(c, poll.message_id)

                await client.edit_message(m, create_message(command.server, poll, db_options))
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
    poll = session.query(models.Poll).filter(models.Poll.poll_id == poll_id).first()

    # Create the message with the poll
    # and delete the previous message
    if poll is not None:
        c = client.get_channel(db_channel.discord_id)

        # Delete this message
        try:
            m = await client.get_message(c, poll.message_id)

            await client.delete_message(m)
        except discord.errors.NotFound:
            pass

        options = session.query(models.Option).filter(models.Option.poll_id == poll.id).order_by(models.Option.position).all()

        msg = await client.send_message(command.channel, create_message(command.server, poll, options))
        poll.message_id = msg.id

        session.commit()

        # Add a reaction for each option, with 9 being the max number of reactions
        emoji = u'\u0031'

        for i in range(min(len(options), 9)):
            await client.add_reaction(msg, emoji + u'\u20E3')
            emoji = chr(ord(emoji) + 1)


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
        db_channel = models.Channel(channel_id)

        session.add(db_channel)
        session.commit()

    msg = 'models.Poll Me Bot Help\n' \
          '----------------\n' \
          'Creating a poll: *!poll poll_id "Question" "Option 1" "Option 2"*\n' \
          'Voting: *!vote poll_id list_of_numbers_separated_by_comma*\n' \
          'Removing votes: *!unvote poll_id list_of_numbers_separated_by_comma*\n' \
          '(More options and details are available at https://github.com/correia55/models.PollMeBot)\n' \
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


def create_message(server, poll, options, selected_options=None):
    """
    Creates a message given a poll.

    :param server: the server where the poll was created.
    :param poll: the poll.
    :param options: the options available in the poll.
    :param selected_options: the list of options that are to be displayed in the closed poll.
    :return: the message that represents the poll.
    """

    if selected_options is not None:
        msg = '**%s** (Closed)' % poll.question
    else:
        m = server.get_member(poll.author)
        msg = '**%s** (poll_id: %s) (author: %s)' % (poll.question, poll.poll_id, m.mention)

    for i in range(len(options)):
        # Ignore the options not selected
        if selected_options is not None:
            if i + 1 not in selected_options:
                continue

        msg += '\n%d - %s' % ((i + 1), options[i].option)

        # Get all votes for that option
        votes = session.query(models.Vote).filter(models.Vote.option_id == options[i].id).all()

        if len(votes) > 0:
            msg += ': %d votes' % len(votes)

            # Show the number of voters for the option
            if poll.only_numbers:
                msg += '.'
            # Show the names of the voters for the option
            else:
                msg += ' ->'

                for v in votes:
                    msg += ' %s' % v.participant_mention

        if options[i].locked:
            msg += ' (locked)'

    if selected_options is None:
        if poll.new_options:
            msg += '\n(New options allowed!)'

        if poll.multiple_options:
            msg += '\n(Multiple options allowed!)'

        if poll.allow_external:
            msg += '\n(External voters allowed!)'

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
    prev_vote = session.query(models.Vote).filter(models.Vote.option_id.in_(ids))\
        .filter(models.Vote.participant_mention == participant).first()

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

        await client.edit_message(m, create_message(None, poll, options, selected_options=selected_options))
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
        channels = session.query(models.Channel).all()

        # Delete all channels that no longer exist
        for channel in channels:
            c = client.get_channel(channel.discord_id)

            if c is None:
                session.delete(channel)

        session.flush()

        polls = session.query(models.Poll).all()

        # Delete all polls that no longer exist
        for poll in polls:
            channel = session.query(models.Channel).filter(models.Channel.id == poll.channel_id).first()

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


async def send_closed_poll_message(options, server, db_poll, channel):
    """
    Send a private message to every member that voted in the poll.

    :param options: options available in the poll.
    :param server: the server where the poll was created.
    :param db_poll: the models.Poll entry from the DB.
    :param channel: the channel where the poll was created.
    """

    ids = []

    for o in options:
        ids.append(o.id)

    # Get all the votes with different participants from this poll
    votes = session.query(models.Vote).filter(models.Vote.option_id.in_(ids))\
        .distinct(models.Vote.participant_id).all()

    # Send a private message to each member that voted
    for v in votes:
        # If it's not an external user
        if v.participant_id is not None:
            m = server.get_member(v.participant_id)

            # If it found the user
            if m is not None:
                # Don't send message to the author
                if v.participant_id != db_poll.author:
                    try:
                        await client.send_message(m, 'models.Poll %s was closed, check the results in %s!'
                                                  % (db_poll.poll_id, channel.mention))
                    except discord.errors.Forbidden:
                        pass


def add_vote(option, participant_id, participant_mention, db_options, multiple_options):
    """
    Add a vote.

    :param option: the voted option.
    :param participant_id: the id of the participant whose vote is to add.
    :param participant_mention: the mention of the participant whose vote is to add.
    :param db_options: the existing options in the db.
    :param multiple_options: if multiple options are allowed in this poll.
    """

    new_vote = False

    # If it is a valid option
    if 0 < option <= len(db_options):
        if db_options[option - 1].locked:
            return False

        vote = session.query(models.Vote)\
            .filter(models.Vote.option_id == db_options[option - 1].id)\
            .filter(models.Vote.participant_mention == participant_mention).first()

        # Vote for an option if multiple options are allowed and he is yet to vote this option
        if multiple_options and vote is None:
            # Add the new vote
            vote = models.Vote(db_options[option - 1].id, participant_id, participant_mention)
            session.add(vote)

            new_vote = True

        # If multiple options are not allowed
        elif not multiple_options:
            # The participant didn't vote this option
            if vote is None:
                remove_prev_vote(db_options, participant_mention)

                # Add the new vote
                vote = models.Vote(db_options[option - 1].id, participant_id, participant_mention)
                session.add(vote)

                new_vote = True

    return new_vote


def remove_vote(option, participant_mention, db_options):
    """
    Remove a vote.

    :param option: the voted option.
    :param participant_mention: the mention of the participant whose vote is to add.
    :param db_options: the existing options in the db.
    """

    vote_removed = False

    # If it is a valid option
    if 0 < option <= len(db_options):
        if db_options[option - 1].locked:
            return False

        vote = session.query(models.Vote)\
            .filter(models.Vote.option_id == db_options[option - 1].id)\
            .filter(models.Vote.participant_mention == participant_mention).first()

        if vote is not None:
            # Remove the vote from this option
            session.delete(vote)

            vote_removed = True

    return vote_removed


def date_given_day(date, day):
    """
    Return the date corresponding to a day.

    :param day: the day.
    """

    last_day_month = (date.replace(month=(date.month + 1) % 12, day=1) - datetime.timedelta(days=1)).day
    last_day_next_month = (date.replace(month=(date.month + 2) % 12, day=1) - datetime.timedelta(days=1)).day

    # It is this month's
    if date.day <= day <= last_day_month:
        date = date.replace(day=day)
    # It is next month's
    elif 0 < day < date.day and day <= last_day_next_month:
        if date.month == 12:
            date = date.replace(year=date.year, month=1, day=day)
        else:
            date = date.replace(month=date.month + 1, day=day)

    return date

# endregion


# Run the bot
client.run(token)
