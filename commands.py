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

    # The id of the Discord channel where the message was sent
    channel_id = command.channel.id

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
        db_channel = models.Channel(channel_id, delete_commands, delete_all)

        config.session.add(db_channel)
    else:
        db_channel.delete_commands = delete_commands
        db_channel.delete_all = delete_all

    config.session.commit()

    print('Channel %s from %s configured!' % (command.channel.name, command.server.name))


async def create_poll_command(command, db_channel):
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
    poll = config.session.query(models.Poll).filter(models.Poll.poll_id == poll_params[0]).first()

    # If a poll with the same id already exists, delete it
    if poll is not None:
        if poll.author == command.author.id:
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

    num_polls = config.session.query(models.Poll).filter(models.Poll.discord_server_id == server_id).count() + \
                config.session.query(models.ClosedPoll).filter(models.Poll.discord_server_id == server_id).count()

    # Limit the number of polls per server
    if num_polls >= config.POLL_LIMIT_SERVER:
        polls = config.session.query(models.Poll).filter(models.Poll.discord_server_id == server_id) \
                       .filter(models.Poll.author == command.author.id).all()
        polls.extend(config.session.query(models.ClosedPoll).filter(models.ClosedPoll.discord_server_id == server_id)
                           .filter(models.Poll.author == command.author.id).all())

        msg = 'The server you\'re in has reached its poll limit, creating another poll is not possible.'

        if len(polls) == 0:
            msg += 'Ask the authors of other polls to delete them.\nYour command: **%s**' % command.content

        else:
            msg += 'Delete one of your polls before continuing.\nList of your polls in this server:'

            for p in polls:
                msg += '\n%s - !poll_delete %s' % (p.poll_id, p.poll_id)

            msg += '\nYour command: **%s**' % command.content

        await auxiliary.send_temp_message(msg, command.channel)
        return

    # Create the new poll
    new_poll = models.Poll(poll_params[0], command.author.id, poll_params[1], multiple_options, only_numbers,
                           new_options, allow_external, db_channel.id, server_id)

    config.session.add(new_poll)

    # Send a private message to each member in the server
    for m in command.server.members:
        if m != config.client.user and m.id != new_poll.author:
            try:
                await config.client.send_message(m, 'A new poll (%s) has been created in %s!'
                                                 % (new_poll.poll_id, command.channel.mention))
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
    msg = await config.client.send_message(command.channel, auxiliary.create_message(command.server, new_poll, options))

    new_poll.message_id = msg.id

    # Add a reaction for each option, with 9 being the max number of reactions
    emoji = u'\u0031'

    for i in range(min(len(options), 9)):
        await config.client.add_reaction(msg, emoji + u'\u20E3')
        emoji = chr(ord(emoji) + 1)

    config.session.commit()

    print('Poll %s created!' % new_poll.poll_id)


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

    poll_id = poll_params[0]

    # Select the current poll
    poll = config.session.query(models.Poll).filter(models.Poll.poll_id == poll_id).first()

    # If no poll was found with that id
    if poll is None:
        msg = 'There\'s no poll with that id for you to edit.\nYour command: **%s**' % command.content

        await auxiliary.send_temp_message(msg, command.channel)
        return

    # Only the author can edit
    if poll.author != command.author.id:
        msg = 'Only the author of a poll can edit it!'

        await auxiliary.send_temp_message(msg, command.channel)
        return

    # Get all options available in the poll
    db_options = config.session.query(models.Option).filter(models.Option.poll_id == poll.id) \
                       .order_by(models.Option.position).all()

    # Add the new options
    if add:
        new_options = poll_params[1:]

        options = []

        # Create the options
        for option in new_options:
            options.append(models.Option(poll.id, len(options) + 1, option))

        config.session.add_all(options)

        # Get the message corresponding to the poll
        c = config.client.get_channel(db_channel.discord_id)
        poll_msg = await config.client.get_message(c, poll.message_id)

        # Add a reaction for each new option
        emoji = chr(ord(u'\u0031') + len(db_options))

        # Max number of reactions that can be added
        num_react = min(9, len(db_options) + len(options))

        for i in range(max(0, num_react - len(db_options))):
            await config.client.add_reaction(poll_msg, emoji + u'\u20E3')
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
            c = config.client.get_channel(db_channel.discord_id)
            poll_msg = await config.client.get_message(c, poll.message_id)

            for option in selected_options:
                num_options = len(db_options)

                # If it is a valid option
                if 0 < option <= num_options:
                    if remove:
                        # Remove the option - needs to be before the removal of reactions or it causes problems
                        config.session.delete(db_options[option - 1])
                        db_options.remove(db_options[option - 1])

                        # Remove the reaction for the highest option
                        if num_options < 10:
                            emoji = chr(ord(u'\u0031') + num_options - 1)

                            users = None

                            # Get all users with that reaction
                            for reaction in poll_msg.reactions:
                                if reaction.emoji == (emoji + u'\u20E3'):
                                    users = await config.client.get_reaction_users(reaction)

                            if users is not None:
                                for user in users:
                                    await config.client.remove_reaction(poll_msg, emoji + u'\u20E3', user)

                            await config.client.remove_reaction(poll_msg, emoji + u'\u20E3', config.client.user)
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
    c = config.client.get_channel(db_channel.discord_id)

    try:
        m = await config.client.get_message(c, poll.message_id)

        await config.client.edit_message(m, auxiliary.create_message(command.server, poll, db_options))
    except discord.errors.NotFound:
        config.session.delete(poll)

    config.session.commit()

    print('Poll %s created!' % poll.poll_id)


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
        poll = config.session.query(models.Poll).filter(models.Poll.poll_id == poll_id).first()

        # Edit the message with the poll
        if poll is not None:
            # Only the author can close the poll
            if poll.author == command.author.id:
                options = config.session.query(models.Option).filter(models.Option.poll_id == poll.id) \
                                 .order_by(models.Option.position).all()

                # Send a private message to all participants in the poll
                await auxiliary.send_closed_poll_message(options, command.server, poll, command.channel)

                await auxiliary.close_poll(command.server, poll, db_channel, options, selected_options)

                config.session.commit()

                print('Poll %s closed!' % poll.poll_id)
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

    poll_id = params[1]

    # Select the current poll
    poll = config.session.query(models.Poll).filter(models.Poll.poll_id == poll_id).first()

    # Check if there's a closed poll with that id
    if poll is None:
        poll = config.session.query(models.ClosedPoll).filter(models.ClosedPoll.poll_id == poll_id).first()

    # Delete the message with the poll
    if poll is not None:
        await auxiliary.delete_poll(poll, db_channel, command.author.id)
    else:
        msg = 'There\'s no poll with that id for you to delete.\nYour command: **%s**' % command.content

        await auxiliary.send_temp_message(msg, command.channel)

    config.session.commit()

    print('Poll %s deleted!' % poll.poll_id)


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
        author_id = None
        author_mention = params[4]

        if author_mention[0] != '"':
            author_mention = '"%s"' % author_mention
    else:
        # If the command has an invalid number of parameters
        if len(params) != 3:
            msg = 'Invalid parameters in command: **%s**' % command.content

            await auxiliary.send_temp_message(msg, command.channel)
            return

        author_id = command.author.id
        author_mention = command.author.mention

    poll_id = params[1]
    options = params[2]

    # Select the current poll
    poll = config.session.query(models.Poll).filter(models.Poll.poll_id == poll_id).first()

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
              'If you need this option, ask the poll author to edit it.' % poll_id

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
            poll_edited |= auxiliary.add_vote(option, author_id, author_mention, db_options, poll.multiple_options)

    # Option is not a list of numbers
    except ValueError:
        if poll.new_options:
            if not poll.multiple_options:
                auxiliary.remove_prev_vote(db_options, author_mention)

            if options[0] == '"' and options[-1] == '"':
                # Remove quotation marks
                options = options.replace('"', '')

                # Add the new option to the poll
                options = models.Option(poll.id, len(db_options) + 1, options)
                db_options.append(options)
                config.session.add(options)

                config.session.flush()

                vote = models.Vote(options.id, author_id, author_mention)
                config.session.add(vote)

                poll_edited = True
        else:
            msg = 'models.Poll *%s* does not allow for new votes.\n' \
                  'If you need this option, ask the poll author to edit it.' % poll_id

            await auxiliary.send_temp_message(msg, command.channel)
            return

    # Edit the message
    if poll_edited:
        c = config.client.get_channel(db_channel.discord_id)

        try:
            m = await config.client.get_message(c, poll.message_id)
            await config.client.edit_message(m, auxiliary.create_message(command.server, poll, db_options))
        except discord.errors.NotFound:
            config.session.delete(poll)

    config.session.commit()

    print('%s voted in %s!' % (author_mention, poll.poll_id))


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
        author_mention = params[4]

        if author_mention[0] != '"':
            author_mention = '"%s"' % author_mention
    else:
        # If the command has an invalid number of parameters
        if len(params) != 3:
            msg = 'Invalid parameters in command: **%s**' % command.content

            await auxiliary.send_temp_message(msg, command.channel)
            return

        author_mention = command.author.mention

    poll_id = params[1]
    options = params[2]

    # Select the current poll
    poll = config.session.query(models.Poll).filter(models.Poll.poll_id == poll_id).first()

    # If no poll was found with that id
    if poll is None:
        msg = 'There\'s no poll with that id for you to remove.\nYour command: **%s**' % command.content

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
            poll_edited |= auxiliary.remove_vote(option, author_mention, db_options)

        if poll_edited:
            # Edit the message
            c = config.client.get_channel(db_channel.discord_id)

            try:
                m = await config.client.get_message(c, poll.message_id)

                await config.client.edit_message(m, auxiliary.create_message(command.server, poll, db_options))
            except discord.errors.NotFound:
                config.session.delete(poll)

            config.session.commit()

            print('%s removed vote from %s!' % (author_mention, poll.poll_id))

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

    poll_id = params[1]

    # Select the current poll
    poll = config.session.query(models.Poll).filter(models.Poll.poll_id == poll_id).first()

    # Check if there's a closed poll with that id
    if poll is None:
        poll = config.session.query(models.ClosedPoll).filter(models.ClosedPoll.poll_id == poll_id).first()

    # Create the message with the poll
    # and delete the previous message
    if poll is not None:
        await auxiliary.refresh_poll(poll, db_channel.discord_id, command.server)


async def help_message_command(command, db_channel):
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

        config.session.add(db_channel)
        config.session.commit()

    msg = 'models.Poll Me Bot Help\n' \
          '----------------\n' \
          'Creating a poll: *!poll poll_id "Question" "Option 1" "Option 2"*\n' \
          'Voting: *!vote poll_id list_of_numbers_separated_by_comma*\n' \
          'Removing votes: *!unvote poll_id list_of_numbers_separated_by_comma*\n' \
          '(More options and details are available at https://github.com/correia55/models.PollMeBot)\n' \
          '(This message will self-destruct in 30 seconds.)'

    await auxiliary.send_temp_message(msg, command.channel)
