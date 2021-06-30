import asyncio

import discord

import auxiliary
import commands
import configuration as config
import interactive
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

    # If it is a reply
    if message.reference:
        # Get the referenced message
        c = config.client.get_channel(message.channel.id)
        referenced_message = await c.fetch_message(message.reference.message_id)

        # If it was an interaction with one of the bot's messages
        if referenced_message.author == config.client.user:
            await interactive.process_reply(message, referenced_message, db_channel)

        return

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
    elif message.content.startswith('!poll_mention '):
        await commands.poll_mention_message_command(message, db_channel)
    elif message.content.startswith('!poll '):
        await commands.create_poll_command(message, db_channel)
    elif message.content.startswith('!vote '):
        await commands.vote_poll_command(message, db_channel)
    elif message.content.startswith('!unvote '):
        await commands.unvote_poll_command(message, db_channel)
    elif message.content.startswith('!help_me_poll'):
        await commands.start_interactive_command(message, db_channel)
    else:
        is_command = False

    # Delete all messages or just commands, depending on the channel settings
    if db_channel is not None:
        try:
            # Delete all messages that were not sent by the bot
            if db_channel.delete_all and message.author != config.client.user:
                await message.delete()
            # Delete all messages associated with a command
            elif db_channel.delete_commands and is_command:
                await message.delete()
        except discord.errors.NotFound:
            pass


# When a reaction is added in Discord
@config.client.event
async def on_reaction_add(reaction: discord.reaction.Reaction, user):
    if user == config.client.user:
        return

    # Select the current poll
    poll = config.session.query(models.Poll).filter(models.Poll.discord_message_id == reaction.message.id).first()

    # The reaction was to a message that is not a poll
    if poll is None:
        # If it was an interaction with one of the bot's messages
        if reaction.message.author == config.client.user:
            await interactive.process_reaction(reaction)

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

    poll_edited = auxiliary.add_vote(option, user.id, db_options, poll.multiple_options)

    # Edit the message
    if poll_edited:
        c = config.client.get_channel(db_channel.discord_id)

        try:
            m = await c.fetch_message(poll.discord_message_id)
            await m.edit(content=auxiliary.create_message(poll, db_options))
        except discord.errors.NotFound:
            config.session.delete(poll)

        config.session.commit()

        print('%s reacted with %d in %s!' % (user.id, option, poll.poll_key))


# When a reaction is removed in Discord
@config.client.event
async def on_reaction_remove(reaction, user):
    if user == config.client.user:
        return

    # Select the current poll
    poll = config.session.query(models.Poll).filter(models.Poll.discord_message_id == reaction.message.id).first()

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
            m = await c.fetch_message(poll.discord_message_id)
            await m.edit(content=auxiliary.create_message(poll, db_options))
        except discord.errors.NotFound:
            config.session.delete(poll)

        config.session.commit()

        print('%s removed reaction %d from %s!' % (user.id, option, poll.poll_key))


# Run the bot
config.client.run(config.token)
