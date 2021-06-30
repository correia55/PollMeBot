import asyncio
import datetime
import random
import re
from typing import List

import discord.reaction

import auxiliary
import commands
import configuration as config
import models

header = 'Poll Me Bot Interactive mode (in Beta) (key:%s)\n' \
         '---------------------------------'

menu_options = ['Create a poll.', 'Check help menu.']


async def process_reaction(reaction: discord.reaction.Reaction):
    """
    Process a reaction to one of the bot's messages.

    :param reaction: the reaction.
    """

    # Get the number of the vote
    option = ord(reaction.emoji[0]) - 49

    if 'key:menu' in reaction.message.content:
        if option < 0 or option >= len(menu_options):
            return

        if option == 0:
            msg = header % 'create_poll' + '\nReply to this message with the title of the poll.'
            await auxiliary.send_temp_message(msg, reaction.message.channel, time=300)
        elif option == 1:
            # Get the channel information from the DB
            db_channel = config.session.query(models.Channel) \
                .filter(models.Channel.discord_id == reaction.message.channel.id).first()

            await commands.help_message_command(reaction.message, db_channel)

    elif 'key:add_options' in reaction.message.content:
        # Get the referenced message
        c = config.client.get_channel(reaction.message.channel.id)
        referenced_message = await c.fetch_message(reaction.message.id)

        if option == 128149:
            # Get the current dates
            start_date = datetime.datetime.today()

            num_options = max(6 - start_date.weekday(), 0)
            end_date = start_date + datetime.timedelta(days=num_options)

            await add_options(auxiliary.create_weekly_options(start_date, end_date), referenced_message)


async def process_reply(reply: discord.message.Message, referenced_message: discord.message.Message,
                        db_channel: models.Channel):
    """
    Process a reply to one of the bot's messages.
    
    :param reply: the reply.
    :param referenced_message: the message being replied.
    :param db_channel: the DB channel in which it was answered.
    """

    if 'key:create_poll' in referenced_message.content:
        await create_poll(reply, db_channel)

    elif 'key:add_options' in referenced_message.content:
        await add_options(reply.content.split(','), referenced_message)
    else:
        return

    # Wait for 300 seconds
    await asyncio.sleep(300)

    # Then delete the reply
    await reply.delete()


async def create_poll(reply: discord.message.Message, db_channel: models.Channel):
    """
    Create a poll from the reply and send a new message asking for the options.

    :param reply: the reply.
    :param db_channel: the DB channel in which it was answered.
    """

    # Create a new poll
    poll_key = reply.content.split()[0] + str(random.getrandbits(8))

    new_poll = models.Poll(poll_key, reply.author.id, reply.content, False,
                           False, False, False, db_channel.id, reply.guild.id)

    config.session.add(new_poll)
    config.session.commit()

    # Send the message
    msg = header % ('add_options)(poll_key:%s)' % poll_key) \
          + '\nReply to this message with the options of the poll, separated by comma (,).\n' \
            'Or use the 📆 reaction to add weekdays as options.'

    message = await reply.channel.send(msg)

    # Add the calendar reaction
    await message.add_reaction('📆')

    # Wait for 300 seconds
    await asyncio.sleep(300)

    # Delete this message
    try:
        await message.delete()
    except discord.errors.NotFound:
        pass


async def add_options(options: List[str], referenced_message: discord.message.Message):
    """
    Add the options in the reply to the poll in the referenced message.

    :param reply: the reply.
    :param referenced_message: the message being replied.
    """

    # Get the poll_key
    poll_key = re.search(r'poll_key:([^)]+)', referenced_message.content).group(1)

    # Get the poll with this key
    db_poll: models.Poll = config.session.query(models.Poll).filter(models.Poll.poll_key == poll_key).first()

    # Create the DB options
    db_options = []

    for i in range(len(options)):
        db_options.append(models.Option(db_poll.id, len(db_options) + 1, options[i].strip()))

    config.session.add_all(db_options)

    # Create the message with the poll
    msg = await referenced_message.channel.send(auxiliary.create_message(db_poll, db_options))

    db_poll.discord_message_id = msg.id

    # Add a reaction for each option
    await auxiliary.add_options_reactions(msg, options)

    config.session.commit()

    print('Poll %s created -> %s!' % (db_poll.poll_key, db_poll.question))
