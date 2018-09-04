import os
token = os.environ.get('BOT_TOKEN', None)

import discord
import asyncio

client = discord.Client()

@client.event
async def on_ready():
    print('Logged in as')
    print(client.user.name)
    print(client.user.id)
    print('------')

class Poll:
    def __init__(self, question, responses):
        self.poll = None
        self.poll_question = question

        if len(responses) > 0:
            self.poll_responses = responses
        else:
            self.poll_responses = ['Yes', 'No']

        self.poll_participants = []

        for i in range(len(self.poll_responses)):
            self.poll_participants.append([])

poll_list = {}

@client.event
async def on_message(message):
    if message.content.startswith('!poll'):
        comps = remove_pair_members(message.content.split('\''))

        new_poll = Poll(comps[0], comps[1:])

        poll_list[message.channel.id] = new_poll

        new_poll.poll = await client.send_message(message.channel, create_message(new_poll))

        #await client.delete_message(message)
    elif message.content.startswith('!answer'):
        if message.channel.id in poll_list:
            poll = poll_list[message.channel.id]

            if message.author not in poll.poll_participants:
                answer = message.content.replace('!answer ', '')

                try:
                    answer = int(answer)

                    if 0 < answer <= len(poll.poll_responses):
                        poll.poll_participants[answer - 1].append(message.author)
                        await client.edit_message(poll.poll, create_message(poll))
                except ValueError:
                    pass

        #await client.delete_message(message)


def remove_pair_members(l):
    num = len(l)

    i = 0
    c = 0

    for i in range(num):
        if i % 2 == 0:
            l.pop(c)
        else:
            c += 1

    return l


def create_message(poll):
    msg = '**%s**' % poll.poll_question
    
    for i in range(len(poll.poll_responses)):
        msg += '\n%s (*!answer %d*)' % (poll.poll_responses[i], (i + 1))

        if len(poll.poll_participants[i]) > 0:
            msg += ':'

            for p in poll.poll_participants[i]:
                msg += ' %s' % p

    return msg


client.run(token)