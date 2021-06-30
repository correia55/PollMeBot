import asyncio
import datetime
from typing import List, Any

import discord

import configuration as config
import models

# Names of weekdays in English and Portuguese
WEEKDAYS_EN = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
WEEKDAYS_PT = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']


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


def create_message(poll, options):
    """
    Creates a message given a poll.

    :param poll: the poll.
    :param options: the options available in the poll.
    :return: the message that represents the poll.
    """

    msg = '**%s** (poll_key: %s) (author: <@%s>)' % (poll.question, poll.poll_key, poll.discord_author_id)

    if poll.closed:
        msg += ' (Closed)'

    for i in range(len(options)):
        msg += '\n%d - %s' % (options[i].position, options[i].option_text)

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
                    if v.participant_name:
                        msg += ' %s' % v.participant_name
                    else:
                        msg += ' <@%s>' % v.discord_participant_id

        if options[i].locked:
            msg += ' (locked)'

    if not poll.closed:
        if poll.new_options:
            msg += '\n(New options allowed!)'

        if poll.multiple_options:
            msg += '\n(Multiple options allowed!)'

        if poll.allow_external:
            msg += '\n(External voters allowed!)'

    return msg


def remove_prev_vote(options, poll_participant):
    """
    Remove the previous vote of a participant.

    :param options: the options available in the poll.
    :param poll_participant: the id of the participant whose vote is to remove.
    """

    ids = []

    for o in options:
        ids.append(o.id)

    # Get the previous vote
    # int means discord used
    # string means external participant
    if type(poll_participant) == str:
        prev_vote = config.session.query(models.Vote).filter(models.Vote.option_id.in_(ids)) \
            .filter(models.Vote.participant_name == poll_participant).first()
    else:
        prev_vote = config.session.query(models.Vote).filter(models.Vote.option_id.in_(ids)) \
            .filter(models.Vote.discord_participant_id == poll_participant).first()

    # If it had voted for something else remove it
    if prev_vote is not None:
        config.session.delete(prev_vote)


async def close_poll(db_poll, db_channel, selected_options):
    """
    Close a poll from the DB and update the message.

    :param db_poll: the poll to close.
    :param db_channel: the corresponding channel entry in the DB.
    :param selected_options: the list of options that are to be displayed in the closed poll.
    """

    # Edit the message to display as closed
    c = config.client.get_channel(db_channel.discord_id)

    try:
        m = await c.fetch_message(db_poll.discord_message_id)

        non_selected_options = config.session.query(models.Option).filter(models.Option.poll_id == db_poll.id) \
            .filter(~models.Option.position.in_(selected_options)).all()

        # Delete all non selected options
        for option in non_selected_options:
            config.session.delete(option)

        config.session.flush()

        # Update options list
        options = config.session.query(models.Option).filter(models.Option.poll_id == db_poll.id) \
            .order_by(models.Option.position).all()

        db_poll.closed = True
        db_poll.closed_date = datetime.date.today()

        new_msg = create_message(db_poll, options)

        await m.edit(content=new_msg)

        await m.clear_reactions()
    except discord.errors.NotFound:
        pass

    config.session.flush()


async def delete_poll(poll, db_channel, command_author):
    """
    Delete a poll and its message.

    :param poll: the poll to delete.
    :param db_channel: the corresponding channel entry in the DB.
    :param command_author: the author of the command.
    """

    # Only the author can delete the poll
    if command_author is None or poll.discord_author_id == command_author:
        c = config.client.get_channel(db_channel.discord_id)

        try:
            m = await c.fetch_message(poll.discord_message_id)

            await m.delete()
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

        if poll.discord_message_id is None:
            config.session.delete(poll)
        else:
            try:
                await c.fetch_message(poll.discord_message_id)
            except discord.errors.NotFound:
                config.session.delete(poll)

    print('Checking for deleted messages and channels...Done')


async def delete_old_closed_polls():
    """
    Delete old closed polls.

    :return:
    """

    polls = config.session.query(models.Poll).filter(models.Poll.closed).all()

    today = datetime.date.today()

    # Delete all polls that no longer exist
    for poll in polls:
        if (today - poll.closed_date).days > config.OLDEST_CLOSED_POLL_DAYS:
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
    msg = await channel.send(message)

    # Wait for 30 seconds
    await asyncio.sleep(time)

    # Delete this message
    try:
        await msg.delete()
    except discord.errors.NotFound:
        pass


async def show_interactive_message(message, channel, options: List[Any], time=300):
    """
    Show a temporary interactive message.

    :param message: the message sent.
    :param channel: the Discord channel.
    :param options: the options list.
    :param time: the time before deleting the temporary message.
    """

    # Send the message
    msg = await channel.send(message)

    # Add a reaction for each option
    await add_options_reactions(msg, options)

    # Wait for 30 seconds
    await asyncio.sleep(time)

    # Delete this message
    try:
        await msg.delete()
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
        .distinct(models.Vote.discord_participant_id, models.Vote.participant_name).all()

    # Send a private message to each member that voted
    for v in votes:
        # If it's not an external user
        if v.discord_participant_id is not None:
            m = server.get_member(v.discord_participant_id)

            # If it found the user
            if m is not None:
                # Don't send message to the author
                if v.discord_participant_id != db_poll.discord_author_id:
                    try:
                        await m.send('models.Poll %s was closed, check the results in %s!'
                                     % (db_poll.poll_key, channel.mention))
                    except discord.errors.Forbidden:
                        pass


def add_vote(option, poll_participant, db_options, multiple_options):
    """
    Add a vote.

    :param option: the voted option.
    :param poll_participant: the id of the participant whose vote is to add.
    :param db_options: the existing options in the db.
    :param multiple_options: if multiple options are allowed in this poll.
    """

    new_vote = False

    # If it is a valid option
    if 0 < option <= len(db_options):
        if db_options[option - 1].locked:
            return False

        # Check the type of participant
        # int means discord used
        # string means external participant
        if type(poll_participant) == str:
            discord_participant_id = None
            participant_name = poll_participant

            vote = config.session.query(models.Vote) \
                .filter(models.Vote.option_id == db_options[option - 1].id) \
                .filter(models.Vote.participant_name == participant_name).first()
        else:
            discord_participant_id = poll_participant
            participant_name = None

            vote = config.session.query(models.Vote) \
                .filter(models.Vote.option_id == db_options[option - 1].id) \
                .filter(models.Vote.discord_participant_id == discord_participant_id).first()

        # Vote for an option if multiple options are allowed and he is yet to vote this option
        if multiple_options and vote is None:
            # Add the new vote
            vote = models.Vote(db_options[option - 1].id, discord_participant_id, participant_name)
            config.session.add(vote)

            new_vote = True

        # If multiple options are not allowed
        elif not multiple_options:
            # The participant didn't vote this option
            if vote is None:
                remove_prev_vote(db_options, poll_participant)

                # Add the new vote
                vote = models.Vote(db_options[option - 1].id, discord_participant_id, participant_name)
                config.session.add(vote)

                new_vote = True

    return new_vote


def remove_vote(option, poll_participant, db_options):
    """
    Remove a vote.

    :param option: the option to remove.
    :param poll_participant: the discord id of the participant whose vote is to remove.
    :param db_options: the existing options in the db.
    """

    vote_removed = False

    # If it is a valid option
    if 0 < option <= len(db_options):
        if db_options[option - 1].locked:
            return False

        # Check the type of participant
        # int means discord user
        # string means external participant
        if type(poll_participant) == str:
            vote = config.session.query(models.Vote) \
                .filter(models.Vote.option_id == db_options[option - 1].id) \
                .filter(models.Vote.participant_name == poll_participant).first()
        else:
            vote = config.session.query(models.Vote) \
                .filter(models.Vote.option_id == db_options[option - 1].id) \
                .filter(models.Vote.discord_participant_id == poll_participant).first()

        if vote is not None:
            # Remove the vote from this option
            config.session.delete(vote)

            vote_removed = True

    return vote_removed


def date_given_day(date, day):
    """
    Return the date corresponding to a day.

    :param date: the date.
    :param day: the day.
    """

    next_month = date.month + 1 if date.month != 12 else 1
    next_next_month = date.month + 2 if date.month < 11 else date.month - 10

    last_day_month = (date.replace(month=next_month, day=1) - datetime.timedelta(days=1)).day
    last_day_next_month = (date.replace(month=next_next_month, day=1) - datetime.timedelta(days=1)).day

    # It is this month's
    if date.day <= day <= last_day_month:
        date = date.replace(day=day)
    # It is next month's
    elif 0 < day < date.day and day <= last_day_next_month:
        if date.month == 12:
            date = date.replace(year=date.year + 1, month=1, day=day)
        else:
            date = date.replace(month=date.month + 1, day=day)

    return date


async def refresh_poll(poll, channel_discord_id):
    """
    Refresh a poll, deleting the current message and creating a new one.

    :param poll: the poll being refreshed.
    :param channel_discord_id: the id of the discord channel.
    """

    c = config.client.get_channel(channel_discord_id)

    # Delete this message
    try:
        m = await c.fetch_message(poll.discord_message_id)

        await m.delete()
    except discord.errors.NotFound:
        pass

    options = config.session.query(models.Option).filter(models.Option.poll_id == poll.id) \
        .order_by(models.Option.position).all()

    msg = await c.send(create_message(poll, options))
    poll.discord_message_id = msg.id

    config.session.commit()

    print('Poll %s refreshed!' % poll.poll_key)

    if not poll.closed:
        # Add a reaction for each option, with 9 being the max number of reactions
        emoji = u'\u0031'

        for i in range(min(len(options), 9)):
            await msg.add_reaction(emoji + u'\u20E3')
            emoji = chr(ord(emoji) + 1)


async def refresh_all_polls():
    """Refresh all polls, making sure reactions still work when the application is restarted."""

    polls = config.session.query(models.Poll).all()

    for p in polls:
        db_channel = config.session.query(models.Channel).filter(models.Channel.id == p.channel_id).first()

        if db_channel is not None:
            await refresh_poll(p, db_channel.discord_id)

    config.session.flush()

    print('Refreshing all polls...Done')


async def remove_reaction(discord_poll_msg, emoji):
    """
    Remove reaction from a poll message.

    :param discord_poll_msg: the message from which the reactions are to be removed.
    :param emoji: the emoji corresponding to the reaction being removed.
    """

    await discord_poll_msg.clear_reaction(emoji + u'\u20E3')


def create_poll_mention_message(poll_option, message, db_poll_id, discord_author_id):
    """
    Create a message mentioning all participants that voted on a specific option of a specific poll.

    :param poll_option: the selected option.
    :param message: the desired message.
    :param db_poll_id: the id of the poll in the DB.
    :param discord_author_id: the discord id of the author of the command.
    """

    option = config.session.query(models.Option).filter(models.Option.poll_id == db_poll_id,
                                                        models.Option.position == poll_option).first()

    # If no option was found
    if option is None:
        return None

    # Get all the votes for the selected option
    votes = config.session.query(models.Vote).filter(models.Vote.option_id == option.id,
                                                     models.Vote.discord_participant_id != discord_author_id).all()

    if len(votes) == 0:
        return None

    msg = '<@%s> would like to tell ' % discord_author_id

    # Send a private message to each member that voted
    for v in votes:
        # If it's not an external user
        if v.discord_participant_id:
            msg += ' <@%s>' % v.discord_participant_id

    msg += ': %s.' % message

    return msg


def create_channel(command: discord.message.Message) -> models.Channel:
    """
    Create a channel in the DB that represents the Discord channel where the message was sent.

    :param command: the message/command.
    """

    # The ids of the Discord channel and server where the message was sent
    discord_channel_id = command.channel.id
    discord_server_id = command.guild.id

    db_channel = models.Channel(discord_channel_id, discord_server_id)

    config.session.add(db_channel)
    config.session.commit()

    return db_channel


async def add_options_reactions(message: discord.message.Message, options: List[Any]):
    """
    Add a reaction for each of the options in the list.
    Maximum number of reactions is 9.

    :param message: the message.
    :param options: the options list.
    """

    # Add a reaction for each option, with 9 being the max number of reactions
    emoji = u'\u0031'

    for i in range(min(len(options), 9)):
        await message.add_reaction(emoji + u'\u20E3')
        emoji = chr(ord(emoji) + 1)


def create_weekly_options(start_date: datetime.date, end_date: datetime.date, pt=False) -> List[str]:
    """
    Create a list of options with the days of the week.

    :param start_date: the starting day for the options.
    :param end_date: the end day for the options.
    :param pt: whether or not the options should be in portuguese. Otherwise, they'll be in english.
    :return: the list of options.
    """

    options = []

    while start_date <= end_date:
        # Name depending on the option used
        if pt:
            day_name = WEEKDAYS_PT[start_date.weekday()]
        else:
            day_name = WEEKDAYS_EN[start_date.weekday()]

        options.append('%s (%s)' % (day_name, start_date.day))
        start_date = start_date + datetime.timedelta(days=1)

    return options
