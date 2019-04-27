import discord
import asyncio
import datetime

import configuration as config
import models


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

    # If it is a closed poll just return the message
    if isinstance(poll, models.ClosedPoll):
        return poll.message

    m = server.get_member(poll.author)

    msg = '**%s** (poll_id: %s) (author: %s)' % (poll.question, poll.poll_id, m.mention)

    if selected_options is not None:
        msg += ' (Closed)'

    for i in range(len(options)):
        # Ignore the options not selected
        if selected_options is not None:
            if i + 1 not in selected_options:
                continue

        msg += '\n%d - %s' % ((i + 1), options[i].option)

        # Get all votes for that option
        votes = config.session.query(models.Vote).filter(models.Vote.option_id == options[i].id).all()

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
    prev_vote = config.session.query(models.Vote).filter(models.Vote.option_id.in_(ids)) \
                       .filter(models.Vote.participant_mention == participant).first()

    # If it had voted for something else remove it
    if prev_vote is not None:
        config.session.delete(prev_vote)


async def close_poll(server, poll, db_channel, options, selected_options):
    """
    Close a poll from the DB and update the message.

    :param server: the server where the poll was created.
    :param poll: the poll to close.
    :param db_channel: the corresponding channel entry in the DB.
    :param options: the list of options available in the poll.
    :param selected_options: the list of options that are to be displayed in the closed poll.
    """

    # Edit the message to display as closed
    c = config.client.get_channel(db_channel.discord_id)

    try:
        m = await config.client.get_message(c, poll.message_id)

        new_msg = create_message(server, poll, options, selected_options=selected_options)

        await config.client.edit_message(m, new_msg)

        await config.client.clear_reactions(m)

        config.session.add(models.ClosedPoll(poll.poll_id, poll.author, new_msg, poll.message_id, poll.channel_id,
                                      poll.discord_server_id, datetime.date.today()))
    except discord.errors.NotFound:
        pass

    # Delete the poll from the DB
    config.session.delete(poll)
    config.session.flush()


async def delete_poll(poll, db_channel, command_author):
    """
    Delete a poll and its message.

    :param poll: the poll to delete.
    :param db_channel: the corresponding channel entry in the DB.
    :param command_author: the author of the command.
    """

    # Only the author can delete the poll
    if command_author is None or poll.author == command_author:
        c = config.client.get_channel(db_channel.discord_id)

        try:
            m = await config.client.get_message(c, poll.message_id)

            await config.client.delete_message(m)
        except discord.errors.NotFound:
            pass

        # Delete the poll from the DB
        config.session.delete(poll)
        config.session.flush()


async def check_messages_exist():
    """
    Check all messages and channels to see if they still exist.

    :return:
    """

    channels = config.session.query(models.Channel).all()

    # Delete all channels that no longer exist
    for channel in channels:
        c = config.client.get_channel(channel.discord_id)

        if c is None:
            config.session.delete(channel)

    config.session.flush()

    polls = config.session.query(models.Poll).all()

    # Delete all polls that no longer exist
    for poll in polls:
        channel = config.session.query(models.Channel).filter(models.Channel.id == poll.channel_id).first()

        c = config.client.get_channel(channel.discord_id)

        try:
            await config.client.get_message(c, poll.message_id)
        except discord.errors.NotFound:
            config.session.delete(poll)

    print('Checking for deleted messages and channels...Done')


async def delete_old_closed_polls():
    """
    Delete old closed polls.

    :return:
    """

    polls = config.session.query(models.ClosedPoll).all()

    today = datetime.date.today()

    # Delete all polls that no longer exist
    for poll in polls:
        if (today - poll.date).days > config.OLDEST_CLOSED_POLL_DAYS:
            channel = config.session.query(models.Channel).filter(models.Channel.id == poll.channel_id).first()
            await delete_poll(poll, channel, None)

    print('Checking for old closed polls...Done')


async def send_temp_message(message, channel, time=30):
    """
    Show a temporary message.

    :param message: the message sent.
    :param channel: the Discord channel.
    :param time: the time before deleting the temporary message.
    """

    # Send the message
    msg = await config.client.send_message(channel, message)

    # Wait for 30 seconds
    await asyncio.sleep(time)

    # Delete this message
    try:
        await config.client.delete_message(msg)
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
    votes = config.session.query(models.Vote).filter(models.Vote.option_id.in_(ids)) \
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
                        await config.client.send_message(m, 'models.Poll %s was closed, check the results in %s!'
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

        vote = config.session.query(models.Vote) \
            .filter(models.Vote.option_id == db_options[option - 1].id) \
            .filter(models.Vote.participant_mention == participant_mention).first()

        # Vote for an option if multiple options are allowed and he is yet to vote this option
        if multiple_options and vote is None:
            # Add the new vote
            vote = models.Vote(db_options[option - 1].id, participant_id, participant_mention)
            config.session.add(vote)

            new_vote = True

        # If multiple options are not allowed
        elif not multiple_options:
            # The participant didn't vote this option
            if vote is None:
                remove_prev_vote(db_options, participant_mention)

                # Add the new vote
                vote = models.Vote(db_options[option - 1].id, participant_id, participant_mention)
                config.session.add(vote)

                new_vote = True

    return new_vote


def remove_vote(option, participant_id, db_options):
    """
    Remove a vote.

    :param option: the option to be removed.
    :param participant_id: the id of the participant whose vote is to remove.
    :param db_options: the existing options in the db.
    """

    vote_removed = False

    # If it is a valid option
    if 0 < option <= len(db_options):
        if db_options[option - 1].locked:
            return False

        vote = config.session.query(models.Vote) \
            .filter(models.Vote.option_id == db_options[option - 1].id) \
            .filter(models.Vote.participant_id == participant_id).first()

        if vote is not None:
            # Remove the vote from this option
            config.session.delete(vote)

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


async def refresh_poll(poll, channel_discord_id, discord_server):
    """
    Refresh a poll, deleting the current message and creating a new one.

    :param poll: the poll being refreshed.
    :param channel_discord_id: the id of the discord channel.
    :param discord_server: the discord server where the channel belongs.
    """

    c = config.client.get_channel(channel_discord_id)

    # Delete this message
    try:
        m = await config.client.get_message(c, poll.message_id)

        await config.client.delete_message(m)
    except discord.errors.NotFound:
        pass

    options = config.session.query(models.Option).filter(models.Option.poll_id == poll.id) \
        .order_by(models.Option.position).all()

    msg = await config.client.send_message(c, create_message(discord_server, poll, options))
    poll.message_id = msg.id

    config.session.commit()

    print('Poll %s refreshed!' % poll.poll_id)

    # Add a reaction for each option, with 9 being the max number of reactions
    emoji = u'\u0031'

    for i in range(min(len(options), 9)):
        await config.client.add_reaction(msg, emoji + u'\u20E3')
        emoji = chr(ord(emoji) + 1)


async def refresh_all_polls():
    """Refresh all polls, making sure reactions still work when the application is restarted."""

    polls = config.session.query(models.Poll).all()

    polls += config.session.query(models.ClosedPoll).all()

    for p in polls:
        db_channel = config.session.query(models.Channel).filter(models.Channel.id == p.channel_id).first()
        s = config.client.get_server(p.discord_server_id)

        if db_channel is not None and s is not None:
            await refresh_poll(p, db_channel.discord_id, s)

    print('Refreshing all polls...Done')
