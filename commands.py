import discord
import datetime

import configuration as config
import auxiliary
import models

# Names of weekdays in English and Portuguese
WEEKDAYS_EN = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
WEEKDAYS_PT = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']


async def configure_channel_command(command, db_channel):
    """
    Configure a channel with the given settings.
    If this channel does not yet exit in the DB, then create it.

    :param command: the command used.
    :param db_channel: the corresponding channel entry in the DB.
    """

    # Make sure the user changing the channel settings is an admin
    if not command.author.server_permissions.administrator:
        msg = 'Only server administrators can change a channel\'s settings.'

        await auxiliary.send_temp_message(msg, command.channel)
        return

    # The ids of the Discord channel and server where the message was sent
    discord_channel_id = command.channel.id
    discord_server_id = command.server.id

    # Get the list of parameters in the message
    params = auxiliary.parse_command_parameters(command.content)

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
        db_channel = models.Channel(discord_channel_id, discord_server_id, delete_commands, delete_all)

        config.session.add(db_channel)
    else:
        db_channel.delete_commands = delete_commands
        db_channel.delete_all = delete_all

    config.session.commit()

    print('Channel %s from %s was configured -> %s!' % (
        command.channel.name, command.server.name, command.content))


async def create_poll_command(command, db_channel):
    """
    Create a new poll.

    :param command: the command used.
    :param db_channel: the corresponding channel entry in the DB.
    """

    # The ids of the Discord channel and server where the message was sent
    discord_channel_id = command.channel.id
    discord_server_id = command.server.id

    # Create channel if it does not already exist
    if db_channel is None:
        db_channel = models.Channel(discord_channel_id, discord_server_id)

        config.session.add(db_channel)

    # Get the list of parameters in the message
    params = auxiliary.parse_command_parameters(command.content)

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

        await auxiliary.send_temp_message(msg, command.channel)
        return

    # Get the poll with this id
    poll = config.session.query(models.Poll).filter(models.Poll.poll_key == poll_params[0]).first()

    # If a poll with the same id already exists, delete it
    if poll is not None:
        if poll.discord_author_id == command.author.id:
            # Confirmation required before deleting a poll
            if confirmation:
                await auxiliary.delete_poll(poll, db_channel, command.author.id)
            else:
                msg = 'A poll with that id already exists add **-y** to your command to confirm the deletion of the ' \
                      'previous poll.\nYour command: **%s**' % command.content

                await auxiliary.send_temp_message(msg, command.channel)
                return
        else:
            msg = 'A poll with that id already exists and you cannot close it because you are not its author!'

            await auxiliary.send_temp_message(msg, command.channel)
            return

    num_polls = config.session.query(models.Poll).filter(models.Poll.discord_server_id == discord_server_id).count()

    # Limit the number of polls per server
    if num_polls >= config.POLL_LIMIT_SERVER:
        polls = config.session.query(models.Poll).filter(models.Poll.discord_server_id == discord_server_id) \
            .filter(models.Poll.discord_author_id == command.author.id).all()

        msg = 'The server you\'re in has reached its poll limit, creating another poll is not possible.'

        if len(polls) == 0:
            msg += 'Ask the authors of other polls to delete them.\nYour command: **%s**' % command.content

        else:
            msg += 'Delete one of your polls before continuing.\nList of your polls in this server:'

            for p in polls:
                msg += '\n%s - !poll_delete %s' % (p.poll_key, p.poll_key)

            msg += '\nYour command: **%s**' % command.content

        await auxiliary.send_temp_message(msg, command.channel)
        return

    # Create the new poll
    new_poll = models.Poll(poll_params[0], command.author.id, poll_params[1], multiple_options, only_numbers,
                           new_options, allow_external, db_channel.id, discord_server_id)

    config.session.add(new_poll)

    # Send a private message to each member in the server
    for m in command.server.members:
        if m != config.client.user and m.id != new_poll.discord_author_id:
            try:
                await config.client.send_message(m, 'A new poll (%s) has been created in %s!'
                                                 % (new_poll.poll_key, command.channel.mention))
            except discord.errors.Forbidden:
                pass

    # Necessary for the options to get the poll id
    config.session.flush()

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
            start_date = auxiliary.date_given_day(start_date, starting_day)

            if len(days) > 1:
                end_day = int(days[1])
                end_date = auxiliary.date_given_day(start_date, end_day)
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

    config.session.add_all(options)

    # Create the message with the poll
    msg = await config.client.send_message(command.channel, auxiliary.create_message(new_poll, options))

    new_poll.discord_message_id = msg.id

    # Add a reaction for each option, with 9 being the max number of reactions
    emoji = u'\u0031'

    for i in range(min(len(options), 9)):
        await config.client.add_reaction(msg, emoji + u'\u20E3')
        emoji = chr(ord(emoji) + 1)

    config.session.commit()

    print('Poll %s created -> %s!' % (new_poll.poll_key, command.content))


async def edit_poll_command(command, db_channel):
    """
    Edit a poll.

    :param command: the command used.
    :param db_channel: the corresponding channel entry in the DB.
    """

    # If the channel does not exist in the DB
    if db_channel is None:
        msg = 'There\'s no poll in this channel for you to edit!'

        await auxiliary.send_temp_message(msg, command.channel)
        return

    # Get the list of parameters in the message
    params = auxiliary.parse_command_parameters(command.content)

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
    if (len(poll_params) < 2 and (add or remove or lock or unlock)) or \
            (len(poll_params) < 1 and not add and not remove and not lock and not unlock):
        msg = 'Invalid parameters in command: **%s**' % command.content

        await auxiliary.send_temp_message(msg, command.channel)
        return

    poll_key = poll_params[0]

    # Select the current poll
    poll = config.session.query(models.Poll).filter(models.Poll.poll_key == poll_key).first()

    # If no poll was found with that id
    if poll is None:
        msg = 'There\'s no poll with that id for you to edit.\nYour command: **%s**' % command.content

        await auxiliary.send_temp_message(msg, command.channel)
        return

    # Only the author can edit
    if poll.discord_author_id != command.author.id:
        msg = 'Only the author of a poll can edit it!'

        await auxiliary.send_temp_message(msg, command.channel)
        return

    edited = ''

    # Get all options available in the poll
    db_options = config.session.query(models.Option).filter(models.Option.poll_id == poll.id) \
        .order_by(models.Option.position).all()

    # Add the new options
    if add:
        new_options = poll_params[1:]

        options = []

        edited = 'new options added %s' % new_options

        # Create the options
        for option in new_options:
            options.append(models.Option(poll.id, len(db_options) + len(options) + 1, option))

        config.session.add_all(options)

        # Get the message corresponding to the poll
        c = config.client.get_channel(db_channel.discord_id)
        discord_poll_msg = await config.client.get_message(c, poll.discord_message_id)

        # Add a reaction for each new option
        emoji = chr(ord(u'\u0031') + len(db_options))

        # Max number of reactions that can be added
        num_react = min(9, len(db_options) + len(options))

        for i in range(max(0, num_react - len(db_options))):
            await config.client.add_reaction(discord_poll_msg, emoji + u'\u20E3')
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

            if remove:
                options = config.session.query(models.Option) \
                    .filter(models.Option.poll_id == poll.id) \
                    .filter(models.Option.position.in_(selected_options)) \
                    .all()

                num_reactions = max(10 - len(db_options) - len(options), 0)

                edited = 'options removed %s' % options

                for option in options:
                    config.session.delete(option)

                # Get the message corresponding to the poll
                c = config.client.get_channel(db_channel.discord_id)
                discord_poll_msg = await config.client.get_message(c, poll.discord_message_id)

                db_options = config.session.query(models.Option).filter(models.Option.poll_id == poll.id) \
                    .order_by(models.Option.position).all()

                for i in range(num_reactions):
                    emoji = chr(ord(u'\u0031') + len(db_options) + i)

                    await auxiliary.remove_reaction(discord_poll_msg, emoji)

                # Update the positions
                pos = 1

                for option in db_options:
                    option.position = pos
                    pos += 1

            elif lock or unlock:
                if lock:
                    edited = 'options %s locked' % selected_options
                else:
                    edited = 'options %s unlocked' % selected_options

                for option in selected_options:
                    num_options = len(db_options)

                    # If it is a valid option
                    if 0 < option <= num_options:
                        if lock:
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

            edited = 'question is now %s' % poll.question
        # Edit poll settings
        else:
            poll.multiple_options = multiple_options
            poll.only_numbers = only_numbers
            poll.new_options = new_options
            poll.allow_external = allow_external

            edited = 'settings multiple_options=%r, only_numbers=%r, new_options=%r, allow_external=%r changed' \
                     % (multiple_options, only_numbers, new_options, allow_external)

    # Edit message
    c = config.client.get_channel(db_channel.discord_id)

    try:
        m = await config.client.get_message(c, poll.discord_message_id)

        await config.client.edit_message(m, auxiliary.create_message(poll, db_options))
    except discord.errors.NotFound:
        config.session.delete(poll)

    config.session.commit()

    print('Poll %s was edited for %s -> %s!' % (poll.poll_key, edited, command.content))


async def close_poll_command(command, db_channel):
    """
    Close a poll.

    :param command: the command used.
    :param db_channel: the corresponding channel entry in the DB.
    """

    # If the channel does not exist in the DB
    if db_channel is None:
        msg = 'There\'s no poll in this channel for you to close!'

        await auxiliary.send_temp_message(msg, command.channel)
        return

    # Get the list of parameters in the message
    params = auxiliary.parse_command_parameters(command.content)

    # If the command has an invalid number of parameters
    if len(params) != 3:
        msg = 'Invalid parameters in command: **%s**' % command.content

        await auxiliary.send_temp_message(msg, command.channel)
        return

    poll_key = params[1]

    # Split the selected options
    list_options = params[2].split(',')

    # Options are all numbers
    try:
        # Verify if the options are numbers
        selected_options = []

        for o in list_options:
            selected_options.append(int(o))

        # Select the current poll
        poll = config.session.query(models.Poll).filter(models.Poll.poll_key == poll_key).first()

        # Edit the message with the poll
        if poll is not None:
            # Only the author can close the poll
            if poll.discord_author_id == command.author.id:
                options = config.session.query(models.Option).filter(models.Option.poll_id == poll.id) \
                    .order_by(models.Option.position).all()

                # Send a private message to all participants in the poll
                await auxiliary.send_closed_poll_message(options, command.server, poll, command.channel)

                await auxiliary.close_poll(poll, db_channel, selected_options)

                config.session.commit()

                print('Poll %s closed -> %s!' % (poll.poll_key, command.content))
        else:
            msg = 'There\'s no poll with that id for you to close.\nYour command: **%s**' % command.content

            await auxiliary.send_temp_message(msg, command.channel)
    except ValueError:
        pass


async def delete_poll_command(command, db_channel):
    """
    Delete a poll.

    :param command: the command used.
    :param db_channel: the corresponding channel entry in the DB.
    """

    # If the channel does not exist in the DB
    if db_channel is None:
        msg = 'There\'s no poll in this channel for you to delete!'

        await auxiliary.send_temp_message(msg, command.channel)
        return

    # Get the list of parameters in the message
    params = auxiliary.parse_command_parameters(command.content)

    # If the command has an invalid number of parameters
    if len(params) != 2:
        msg = 'Invalid parameters in command: **%s**' % command.content

        await auxiliary.send_temp_message(msg, command.channel)
        return

    poll_key = params[1]

    # Select the current poll
    poll = config.session.query(models.Poll).filter(models.Poll.poll_key == poll_key).first()

    # Delete the message with the poll
    if poll is not None:
        await auxiliary.delete_poll(poll, db_channel, command.author.id)

        config.session.commit()

        print('Poll %s deleted -> %s!' % (poll.poll_key, command.content))
    else:
        msg = 'There\'s no poll with that id for you to delete.\nYour command: **%s**' % command.content

        await auxiliary.send_temp_message(msg, command.channel)


async def vote_poll_command(command, db_channel):
    """
    models.Vote a list of options in a poll.

    :param command: the command used.
    :param db_channel: the corresponding channel entry in the DB.
    """

    # If the channel does not exist in the DB
    if db_channel is None:
        msg = 'There\'s no poll in this channel for you to vote!'

        await auxiliary.send_temp_message(msg, command.channel)
        return

    # Get the list of parameters in the message
    params = auxiliary.parse_command_parameters(command.content)

    # Check for external voters
    if params.__contains__('-e') and len(params) == 5:
        author_id = params[4]

        if author_id[0] != '"':
            author_id = '"%s"' % author_id
    else:
        # If the command has an invalid number of parameters
        if len(params) != 3:
            msg = 'Invalid parameters in command: **%s**' % command.content

            await auxiliary.send_temp_message(msg, command.channel)
            return

        author_id = command.author.id

    poll_key = params[1]
    options = params[2]

    # Select the current poll
    poll = config.session.query(models.Poll).filter(models.Poll.poll_key == poll_key).first()

    # If no poll was found with that id
    if poll is None:
        msg = 'There\'s no poll with that id for you to vote.\nYour command: **%s**' % command.content

        await auxiliary.send_temp_message(msg, command.channel)
        return

    # Get all options available in the poll
    db_options = config.session.query(models.Option).filter(models.Option.poll_id == poll.id) \
        .order_by(models.Option.position).all()

    # If it is an vote for an external user and it is not allowed
    if author_id is None and not poll.allow_external:
        msg = 'models.Poll *%s* does not allow for external votes.\n' \
              'If you need this option, ask the poll author to edit it.' % poll_key

        await auxiliary.send_temp_message(msg, command.channel)
        return

    poll_edited = False

    # Option is a list of numbers
    try:
        # Verify if the options are numbers
        selected_options = []

        for o in options.split(','):
            selected_options.append(int(o))

        for option in selected_options:
            poll_edited |= auxiliary.add_vote(option, author_id, db_options, poll.multiple_options)

    # Option is not a list of numbers
    except ValueError:
        if poll.new_options:
            if not poll.multiple_options:
                auxiliary.remove_prev_vote(db_options, author_id)

            if options[0] == '"' and options[-1] == '"':
                # Remove quotation marks
                options = options.replace('"', '')

                # Add the new option to the poll
                options = models.Option(poll.id, len(db_options) + 1, options)
                db_options.append(options)
                config.session.add(options)

                config.session.flush()

                vote = models.Vote(options.id, author_id)
                config.session.add(vote)

                poll_edited = True
        else:
            msg = 'models.Poll *%s* does not allow for new votes.\n' \
                  'If you need this option, ask the poll author to edit it.' % poll_key

            await auxiliary.send_temp_message(msg, command.channel)
            return

    # Edit the message
    if poll_edited:
        c = config.client.get_channel(db_channel.discord_id)

        try:
            m = await config.client.get_message(c, poll.discord_message_id)
            await config.client.edit_message(m, auxiliary.create_message(poll, db_options))
        except discord.errors.NotFound:
            config.session.delete(poll)

    config.session.commit()

    print('%s voted in %s -> %s!' % (author_id, poll.poll_key, command.content))


async def unvote_poll_command(command, db_channel):
    """
    Remove a vote from an option in a poll.

    :param command: the command used.
    :param db_channel: the corresponding channel entry in the DB.
    """

    # If the channel does not exist in the DB
    if db_channel is None:
        msg = 'There\'s no poll in this channel for you to unvote!'

        await auxiliary.send_temp_message(msg, command.channel)
        return

    # Get the list of parameters in the message
    params = auxiliary.parse_command_parameters(command.content)

    # Check for external voters
    if params.__contains__('-e') and len(params) == 5:
        author_id = params[4]

        if author_id[0] != '"':
            author_id = '"%s"' % author_id
    else:
        # If the command has an invalid number of parameters
        if len(params) != 3:
            msg = 'Invalid parameters in command: **%s**' % command.content

            await auxiliary.send_temp_message(msg, command.channel)
            return

        author_id = command.author.id

    poll_key = params[1]
    options = params[2]

    # Select the current poll
    poll = config.session.query(models.Poll).filter(models.Poll.poll_key == poll_key).first()

    # If no poll was found with that id
    if poll is None:
        msg = 'There\'s no poll with that id for you to unvote.\nYour command: **%s**' % command.content

        await auxiliary.send_temp_message(msg, command.channel)
        return

    # Get all options available in the poll
    db_options = config.session.query(models.Option).filter(models.Option.poll_id == poll.id) \
        .order_by(models.Option.position).all()

    poll_edited = False

    # Option is a number
    try:
        # Verify if the options are numbers
        selected_options = []

        for o in options.split(','):
            selected_options.append(int(o))

        for option in selected_options:
            poll_edited |= auxiliary.remove_vote(option, author_id, db_options)

        if poll_edited:
            # Edit the message
            c = config.client.get_channel(db_channel.discord_id)

            try:
                m = await config.client.get_message(c, poll.discord_message_id)

                await config.client.edit_message(m, auxiliary.create_message(poll, db_options))
            except discord.errors.NotFound:
                config.session.delete(poll)

            config.session.commit()

            print('%s removed vote from %s -> %s!' % (author_id, poll.poll_key, command.content))

    # Option is not a number
    except ValueError:
        pass


async def refresh_poll_command(command, db_channel):
    """
    Show a pole in a new message.

    :param command: the command used.
    :param db_channel: the corresponding channel entry in the DB.
    """

    # If the channel does not exist in the DB
    if db_channel is None:
        msg = 'There\'s no poll in this channel for you to refresh!'

        await auxiliary.send_temp_message(msg, command.channel)
        return

    # Get the list of parameters in the message
    params = auxiliary.parse_command_parameters(command.content)

    # If the command has an invalid number of parameters
    if len(params) != 2:
        msg = 'Invalid parameters in command: **%s**' % command.content

        await auxiliary.send_temp_message(msg, command.channel)
        return

    poll_key = params[1]

    # Select the current poll
    poll = config.session.query(models.Poll).filter(models.Poll.poll_key == poll_key).first()

    # Create the message with the poll
    # and delete the previous message
    if poll is not None:
        await auxiliary.refresh_poll(poll, db_channel.discord_id)

        print('Poll %s refreshed -> %s!' % (poll.poll_key, command.content))


async def poll_mention_message_command(command, db_channel):
    """
    Create a message mentioning the voters of a given option.

    :param command: the command used.
    :param db_channel: the corresponding channel entry in the DB.
    """

    # If the channel does not exist in the DB
    if db_channel is None:
        db_channel = models.Channel(command.channel.id, command.server.id)

        config.session.add(db_channel)
        config.session.commit()

    # Get the list of parameters in the message
    params = auxiliary.parse_command_parameters(command.content)

    # If the command has an invalid number of parameters
    if len(params) != 4:
        msg = 'Invalid parameters in command: **%s**' % command.content

        await auxiliary.send_temp_message(msg, command.channel)
        return

    poll_key = params[1]
    message = params[3]

    try:
        poll_option = int(params[2])

        # Select the current poll
        poll = config.session.query(models.Poll).filter(models.Poll.poll_key == poll_key,
                                                        models.Poll.discord_server_id == command.server.id).first()

        if poll is not None:
            msg = auxiliary.create_poll_mention_message(poll_option, message, poll.id, command.author.id)

            if msg is not None:
                await config.client.send_message(command.channel, msg)
        else:
            msg = 'There\'s no poll with that id for you to mention.\nYour command: **%s**' % command.content

            await auxiliary.send_temp_message(msg, command.channel)
    except ValueError:
        pass


async def help_message_command(command, db_channel):
    """
    Show a help message with the available commands.

    :param command: the command used.
    :param db_channel: the corresponding channel entry in the DB.
    """

    # The ids of the Discord channel and server where the message was sent
    discord_channel_id = command.channel.id
    discord_server_id = command.server.id

    # Create channel if it doesn't already exist
    if db_channel is None:
        db_channel = models.Channel(discord_channel_id, discord_server_id)

        config.session.add(db_channel)
        config.session.commit()

    msg = 'Poll Me Bot Help\n' \
          '----------------\n' \
          'Creating a poll: *!poll poll_key "Question" "Option 1" "Option 2"*\n' \
          'Voting: *!vote poll_key list_of_numbers_separated_by_comma*\n' \
          'Removing votes: *!unvote poll_key list_of_numbers_separated_by_comma*\n' \
          '(More options and details are available at https://github.com/correia55/models.PollMeBot)\n' \
          '(This message will self-destruct in 30 seconds.)'

    await auxiliary.send_temp_message(msg, command.channel)
