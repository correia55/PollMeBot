import os
import shlex
import discord
import asyncio

# Get the token for the bot saved in the environment variable
token = os.environ.get('BOT_TOKEN', None)

if token is None:
    print ('Unable to find bot token!')
    exit(1)

# List of all channels with polls
channel_list = {}

# Create a client
client = discord.Client()

# Class to save configurations specific to the channel and applicable to all polls
class Channel:
    def __init__(self, delete_commands=False, delete_all=False):
        self.delete_all = delete_all

        if delete_all:
            self.delete_commands = False
        elif delete_commands:
            self.delete_commands = True
        else:
            self.delete_commands = False

        # List of all polls in the channel
        self.poll_list = []


# Class to save all the information relative to a single poll
class Poll:
    def __init__(self, poll_id, question, options, multiple_options, only_numbers, new_options):
        self.message_id = None
        self.question = question
        self.poll_id = poll_id

        # If there are no options the default options are Yes and No
        if len(options) > 0:
            self.options = options
        else:
            self.options = ['Yes', 'No']

        # Create a list for participants for each option
        self.participants = []

        for i in range(len(self.options)):
            self.participants.append([])

        # Set the configuration options
        self.multiple_options = multiple_options
        self.only_numbers = only_numbers

        self.new_options = new_options

# region Events

# When the bot has started
@client.event
async def on_ready():
    print('The bot is ready to poll!\n-------------------------')


# When a message is written in Discord
@client.event
async def on_message(message):
    # Configure the channel
    if message.content.startswith('!poll_me_channel'):
        await configure_channel(message)
    # Start a new poll
    elif message.content.startswith('!poll'):
        await create_poll(message)
    # Vote in the current poll
    elif message.content.startswith('!vote '):  # Extra space is necessary
        if message.channel.id in channel_list:
            await vote_poll(message)
    # Remove a vote from the current poll
    elif message.content.startswith('!unvote'):
        if message.channel.id in channel_list:
            await remove_vote(message)
    # Show the current poll in a new message
    elif message.content.startswith('!refresh '):  # Extra space is necessary
        if message.channel.id in channel_list:
            await refresh_poll(message)
    # Remove a vote from the current poll
    elif message.content.startswith('!help_me_poll'):
        await help_message(message)

    # Delete all messages
    if message.channel.id in channel_list:
        channel = channel_list[message.channel.id]

        if channel.delete_all and message.author != client.user:
            await client.delete_message(message)

# endregion

# region Commands

# Configure the channel
async def configure_channel(message):
    channel_id = message.channel.id
    comps = message.content.split(' ')

    if len(comps) != 2:
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
    if channel_id not in channel_list:
        channel_list[channel_id] = Channel(delete_commands, delete_all)
    else:
        channel = channel_list[channel_id]

        channel.delete_commands = delete_commands
        channel.delete_all = delete_all

    # Delete the message that contains this command
    if channel.delete_commands:
        await client.delete_message(message)


# Create a new poll
async def create_poll(message):
    channel_id = message.channel.id

    # Create channel if it doesn't already exist
    if channel_id not in channel_list:
        channel_list[channel_id] = Channel()

    channel = channel_list[channel_id]

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
    new_poll = Poll(poll_comps[0], poll_comps[1], poll_comps[2:], multiple_options, only_numbers, new_options)

    # Limit the number of polls to 5 per channel
    if len(channel.poll_list) == 5:
        channel.poll_list.remove(0)

    # Add the poll to the list
    channel.poll_list.append(new_poll)

    # Create the message with the poll
    new_poll.message_id = await client.send_message(message.channel, create_message(new_poll))

    # Delete the message that contains this command
    if channel.delete_commands:
        await client.delete_message(message)


# Vote in the current poll
async def vote_poll(message):
    channel = channel_list[message.channel.id]

    # Split the command using spaces, ignoring those between quotation marks
    option = message.content.replace('!vote ', '')

    space_pos = option.find(' ')

    # There is no space
    if space_pos == -1:
        return

    poll_id = option[0:space_pos]
    option = option[space_pos + 1:]

    # Select the correct poll
    poll = get_poll(channel, poll_id)

    # If no poll was found with that id
    if poll is None:
        return

    # If the option is empty
    if len(option) == 0:
        if channel.delete_commands:
            await client.delete_message(message)

        return

    # Option is a number
    try:
        option = int(option)

        # If it is a valid option
        if 0 < option <= len(poll.options):
            # Vote for an option if multiple options are allowed and he is yet to vote this option
            if poll.multiple_options and message.author not in poll.participants[option - 1]:
                poll.participants[option - 1].append(message.author)
                await client.edit_message(poll.message_id, create_message(poll))
            # If multiple options are not allowed
            elif not poll.multiple_options:
                # The participant didn't vote this option
                if message.author not in poll.participants[option - 1]:
                    remove_prev_vote(poll, message.author)

                    poll.participants[option - 1].append(message.author)
                    await client.edit_message(poll.message_id, create_message(poll))

    # Option is not a number
    except ValueError:
        if poll.new_options:
            if not poll.multiple_options:
                remove_prev_vote(poll, message.author)

            if option[0] == '"' and option[-1] == '"':
                # Remove quotation marks
                option = option.replace('"', '')

                # Add the new option to the poll
                poll.options.append(option)
                poll.participants.append([message.author])

                await client.edit_message(poll.message_id, create_message(poll))

    # Delete the message that contains this command
    if channel.delete_commands:
        await client.delete_message(message)


# Remove a vote from the current poll
async def remove_vote(message):
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
    poll = get_poll(channel, poll_id)

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
            if message.author in poll.participants[option - 1]:
                # Remove the vote from this option
                poll.participants[option - 1].remove(message.author)
                await client.edit_message(poll.message_id, create_message(poll))

    # Option is not a number
    except ValueError:
        pass

    # Delete the message that contains this command
    if channel.delete_commands:
        await client.delete_message(message)


# Show the current poll in a new message
async def refresh_poll(message):
    channel = channel_list[message.channel.id]

    poll_id = message.content.replace('!refresh ', '')

    # Select the current poll for that channel
    poll = get_poll(channel, poll_id)

    # Create the message with the poll
    if poll is not None:
        poll.message_id = await client.send_message(message.channel, create_message(poll))

    # Delete the message that contains this command
    if channel.delete_commands:
        await client.delete_message(message)


# Show a help message with the available commands
async def help_message(message):
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
def create_message(poll):
    msg = '**%s** (poll_id: %s)' % (poll.question, poll.poll_id)

    for i in range(len(poll.options)):
        msg += '\n%d - %s' % ((i + 1), poll.options[i])

        if len(poll.participants[i]) > 0:
            msg += ':'

            # Show the number of voters for the option
            if poll.only_numbers:
                msg += ' %d vote.' % len(poll.participants[i])
            # Show the names of the voters for the option
            else:
                for p in poll.participants[i]:
                    msg += ' %s' % p.mention

    if poll.new_options:
        msg += '\n(New options can be suggested!)'

    if poll.multiple_options:
        msg += '\n(You can vote on multiple options!)'

    return msg


# Remove the previous vote of a participant
def remove_prev_vote(poll, participant):
    prev_vote = -1

    for i in range(len(poll.options)):
        if participant in poll.participants[i]:
            prev_vote = i
            break

    # If it had voted for something else
    # remove the previous vote
    if prev_vote != -1:
        poll.participants[prev_vote].remove(participant)


# Get the poll with the given poll id
def get_poll(channel, poll_id):
    for i in range(len(channel.poll_list) - 1, -1, -1):
        if channel.poll_list[i].poll_id == poll_id:
            return channel.poll_list[i]

    return None


# endregion


client.run(token)