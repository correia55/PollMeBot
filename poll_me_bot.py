import asyncio
import discord

import configuration as config
import commands
import auxiliary
import models


# When the bot is ready to work
@config.client.event
async def on_ready():
    print('The bot is ready to poll!\n-------------------------')

    refreshed = False

    while True:
        # Check if the messages still exist
        await auxiliary.check_messages_exist()

        # Delete old closed polls
        await auxiliary.delete_old_closed_polls()

        if not refreshed:
            refreshed = True
            await auxiliary.refresh_all_polls()

        config.session.commit()

        await asyncio.sleep(config.TIME_BETWEEN_CHECKS_SEC)


# When a message is written in Discord
@config.client.event
async def on_message(message):
    # Get the channel information from the DB
    db_channel = config.session.query(models.Channel).filter(models.Channel.discord_id == message.channel.id).first()

    is_command = True

    # Check if it is a command and call the correct function to treat it
    if message.content.startswith('!poll_channel '):
        await commands.configure_channel_command(message, db_channel)
    elif message.content.startswith('!poll_edit '):
        await commands.edit_poll_command(message, db_channel)
    elif message.content.startswith('!poll_close '):
        await commands.close_poll_command(message, db_channel)
    elif message.content.startswith('!poll_delete '):
        await commands.delete_poll_command(message, db_channel)
    elif message.content.startswith('!poll_refresh '):
        await commands.refresh_poll_command(message, db_channel)
    elif message.content.startswith('!poll '):
        await commands.create_poll_command(message, db_channel)
    elif message.content.startswith('!vote '):
        await commands.vote_poll_command(message, db_channel)
    elif message.content.startswith('!unvote '):
        await commands.unvote_poll_command(message, db_channel)
    elif message.content.startswith('!help_me_poll'):
        await commands.help_message_command(message, db_channel)
    else:
        is_command = False

    # Delete all messages or just commands, depending on the channel settings
    if db_channel is not None:
        try:
            # Delete all messages that were not sent by the bot
            if db_channel.delete_all and message.discord_author_id != config.client.user:
                await config.client.delete_message(message)
            # Delete all messages associated with a command
            elif db_channel.delete_commands and is_command:
                await config.client.delete_message(message)
        except discord.errors.NotFound:
            pass


# When a reaction is added in Discord
@config.client.event
async def on_reaction_add(reaction, user):
    if user == config.client.user:
        return

    # Select the current poll
    poll = config.session.query(models.Poll).filter(models.Poll.message_id == reaction.message.id).first()

    # The reaction was to a message that is not a poll
    if poll is None:
        return

    # Get the number of the vote
    option = ord(reaction.emoji[0]) - 48

    if option > 9:
        return

    # Get all options available in the poll
    db_options = config.session.query(models.Option).filter(models.Option.poll_id == poll.id) \
                       .order_by(models.Option.position).all()

    # Get the channel information from the DB
    db_channel = config.session.query(models.Channel).filter(models.Channel.discord_id == reaction.message.channel.id) \
                       .first()

    poll_edited = auxiliary.add_vote(option, user.id, user.mention, db_options, poll.multiple_options)

    # Edit the message
    if poll_edited:
        c = config.client.get_channel(db_channel.discord_id)

        try:
            m = await config.client.get_message(c, poll.message_id)
            await config.client.edit_message(m, auxiliary.create_message(reaction.message.server, poll, db_options))
        except discord.errors.NotFound:
            config.session.delete(poll)

        config.session.commit()

        print('%s reacted in %s!' % (user.mention, poll.poll_id))


# When a reaction is removed in Discord
@config.client.event
async def on_reaction_remove(reaction, user):
    if user == config.client.user:
        return

    # Select the current poll
    poll = config.session.query(models.Poll).filter(models.Poll.message_id == reaction.message.id).first()

    # The reaction was to a message that is not a poll
    if poll is None:
        return

    # Get the number of the vote
    option = ord(reaction.emoji[0]) - 48

    if option > 9:
        return

    # Get all options available in the poll
    db_options = config.session.query(models.Option).filter(models.Option.poll_id == poll.id) \
                       .order_by(models.Option.position).all()

    # Get the channel information from the DB
    db_channel = config.session.query(models.Channel).filter(models.Channel.discord_id == reaction.message.channel.id) \
                       .first()

    poll_edited = auxiliary.remove_vote(option, user.id, db_options)

    # Edit the message
    if poll_edited:
        c = config.client.get_channel(db_channel.discord_id)

        try:
            m = await config.client.get_message(c, poll.message_id)
            await config.client.edit_message(m, auxiliary.create_message(reaction.message.server, poll, db_options))
        except discord.errors.NotFound:
            config.session.delete(poll)

        config.session.commit()

        print('%s removed reaction from %s!' % (user.mention, poll.poll_id))

# Run the bot
config.client.run(config.token)
