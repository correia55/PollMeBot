import os
import shlex
import discord
import asyncio

# Create a client
client = discord.Client()

# Get the token for the bot saved in the environment variable
token = os.environ.get('BOT_TOKEN', None)

if token is None:
    print ('Unable to find bot token!')
    exit(1)

# List of all current polls
poll_list = {}

# Class to save all the information relative to a single poll
class Poll:
    def __init__(self, question, options, multiple_options, only_numbers, delete_messages, new_options):
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
        self.delete_messages = delete_messages
        self.new_options = new_options

# When the bot has started
@client.event
async def on_ready():
    print('The bot is ready to poll!\n-------------------------')

# When a message is written in Discord
@client.event
async def on_message(message):
    # Start a new poll
    if message.content.startswith('!poll'):
        comps = shlex.split(message.content)[1:]

        multiple_options = false
        only_numbers = false
        delete_messages = false
        new_options = false

        poll_comps = []

        # Filter the available options for polls
        for i in range(len(comps)):
            if comps[i] == '-mo':
                multiple_options = true
            elif comps[i] == '-on':
                only_numbers = true
            elif comps[i] == '-dm':
                delete_messages = true
            elif comps[i] == '-no':
                new_options = true
            else:
                poll_comps.append(comps[i])

        # Create the new poll
        new_poll = Poll(poll_comps[0], poll_comps[1:], multiple_options, only_numbers, delete_messages, new_options)

        # Add the poll to the list
        poll_list[message.channel.id] = new_poll

        # Create the message with the poll
        new_poll.message_id = await client.send_message(message.channel, create_message(new_poll))

        # Delete the message that contains this command
        if new_poll.delete_messages:
            await client.delete_message(message)
    # Answer to the current poll
    elif message.content.startswith('!answer'):
        if message.channel.id in poll_list:
            # Select the current poll for that channel
            poll = poll_list[message.channel.id]

            # If it allows multiple options or this participant is yet to answer
            if poll.multiple_options or message.author not in poll.participants:
                option = shlex.split(message.content)[1]

                # Option is a number
                try:
                    option = int(option)

                    if 0 < option <= len(poll.options):
                        # Answer an option if multiple options are allowed and he is yet to answer this option
                        if poll.multiple_options and message.author not in poll.participants[option - 1]:
                            poll.participants[option - 1].append(message.author)
                            await client.edit_message(poll.message_id, create_message(poll))
                        # If multiple options are not allowed
                        elif not poll.multiple_options:
                            # The participant didn't answer this option
                            if message.author not in poll.participants[option - 1]:
                                prev_answer = -1

                                for i in range(len(poll.options)):
                                    if message.author in poll.participants[i]:
                                        prev_answer = i
                                        break

                                # If it had answered something else
                                # remove the previous answer
                                if prev_answer != -1:
                                    poll.participants[prev_answer].remove(message.author)

                                poll.participants[option - 1].append(message.author)
                                await client.edit_message(poll.message_id, create_message(poll))

                # Option is not a number
                except ValueError:
                    if poll.new_options:
                        # Add the new option to the poll
                        poll.options.append(option)
                        poll.participants.append([message.author])

            # Delete the message that contains this command
            if poll.delete_messages:
                await client.delete_message(message)


# Creates a message given a poll
def create_message(poll):
    msg = '**%s**' % poll.question
    
    for i in range(len(poll.options)):
        msg += '\n%d - %s (*!answer %d*)' % ((i + 1), poll.options[i], (i + 1))

        if len(poll.participants[i]) > 0:
            msg += ':'

            # Show the number of voters for the option
            if poll.only_numbers:
                msg += '%d' % len(poll.participants)
            # Show the names of the voters for the option
            else:
                for p in poll.participants[i]:
                    msg += ' %s' % p

    return msg

client.run(token)