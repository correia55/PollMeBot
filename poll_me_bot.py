import os
import shlex
import discord
import asyncio

# Get the token for the bot saved in the environment variable
token = os.environ.get('BOT_TOKEN', None)

if token is None:
    print ('Unable to find bot token!')
    exit(1)

# List of all current polls
poll_list = {}

# Create a client
client = discord.Client()

# Class to save all the information relative to a single poll
class Poll:
    def __init__(self, question, options, multiple_options, only_numbers, delete_commands, delete_all, new_options):
        self.message_id = None
        self.question = question

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
        self.delete_all = delete_all

        if delete_all:
            self.delete_commands = False
        else:
            self.delete_commands = delete_commands

        self.new_options = new_options

# region Events

# When the bot has started
@client.event
async def on_ready():
    print('The bot is ready to poll!\n-------------------------')


# When a message is written in Discord
@client.event
async def on_message(message):
    # Start a new poll
    if message.content.startswith('!poll'):
        await create_poll(message)
    # Vote in the current poll
    elif message.content.startswith('!vote '):  # Extra space is necessary
        if message.channel.id in poll_list:
            await vote_poll(message)
    # Remove a vote from the current poll
    elif message.content.startswith('!unvote'):
        if message.channel.id in poll_list:
            await remove_vote(message)
    # Show the current poll in a new message
    elif message.content.startswith('!refresh'):
        if message.channel.id in poll_list:
            await refresh_poll(message)
    # Remove a vote from the current poll
    elif message.content.startswith('!help_me_poll'):
        await help_message(message)

    # Delete all messages
    if message.channel.id in poll_list:
        poll = poll_list[message.channel.id]

        if poll.delete_all and message.author != client.user:
            await client.delete_message(message)

# endregion

# region Commands

# Create a new poll
async def create_poll(message):
    # Split the command using spaces, ignoring those between quotation marks
    comps = shlex.split(message.content)[1:]

    if len(comps) < 1:
        return

    multiple_options = False
    only_numbers = False
    delete_commands = False
    delete_all = False
    new_options = False

    poll_comps = []

    # Filter the available options for polls
    for i in range(len(comps)):
        if comps[i] == '-m':
            multiple_options = True
        elif comps[i] == '-o':
            only_numbers = True
        elif comps[i] == '-dc':
            delete_commands = True
        elif comps[i] == '-da':
            delete_all = True
        elif comps[i] == '-n':
            new_options = True
        else:
            poll_comps.append(comps[i])

    # Create the new poll
    new_poll = Poll(poll_comps[0], poll_comps[1:], multiple_options, only_numbers, delete_commands, delete_all,
                    new_options)

    # Add the poll to the list
    poll_list[message.channel.id] = new_poll

    # Create the message with the poll
    new_poll.message_id = await client.send_message(message.channel, create_message(new_poll))

    # Delete the message that contains this command
    if new_poll.delete_commands:
        await client.delete_message(message)


# Vote in the current poll
async def vote_poll(message):
    # Select the current poll for that channel
    poll = poll_list[message.channel.id]

    # Split the command using spaces, ignoring those between quotation marks
    option = message.content.replace('!vote ', '')

    if len(option) == 0:
        if poll.delete_commands:
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
    if poll.delete_commands:
        await client.delete_message(message)
        

# Remove a vote from the current poll
async def remove_vote(message):
    # Select the current poll for that channel
    poll = poll_list[message.channel.id]

    # Split the command using spaces, ignoring those between quotation marks
    option = shlex.split(message.content)

    if len(option) != 2:
        if poll.delete_commands:
            await client.delete_message(message)

        return

    # Get the inserted option
    option = option[1]

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
    if poll.delete_commands:
        await client.delete_message(message)


# Show the current poll in a new message
async def refresh_poll(message):
    # Select the current poll for that channel
    poll = poll_list[message.channel.id]

    # Create the message with the poll
    poll.message_id = await client.send_message(message.channel, create_message(poll))


# Show a help message with the available commands
async def help_message(message):
    msg = 'Poll Me Bot Help\n' \
          '----------------\n' \
          'For creating a poll: *!poll "Question" "Option 1" "Option 2"*\n' \
          'For voting for an option: *!vote number*\n' \
          'For removing your vote for that option: *!unvote number*\n' \
          '(More options and details are available at https://github.com/correia55/PollMeBot)\n' \
          '(This message will self-destruct in 30 seconds.)'

    # Create the message with the help
    message_id = await client.send_message(message.channel, msg)

    # Wait for 30 seconds
    await asyncio.sleep(30)

    # Delete this message
    await client.delete_message(message_id)

# endregion

# region Auxiliary Functions

# Creates a message given a poll
def create_message(poll):
    msg = '**%s**' % poll.question
    
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

# endregion


client.run(token)