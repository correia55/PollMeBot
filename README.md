# Poll Me Bot - for Discord

A bot, for Discord, that allows you and your friends to create polls and vote.

## Available Commands

Commands start with an exclamation mark (!) followed by the command and then each parameter separated by a space. If a parameter contains spaces, it should be written within quotation marks ("), otherwise it will be split into multiple parameters.

### Configure Channel

```
!poll_channel <setting>
```

Available *settings* for the channel configuration include:
* -dc - all messages with commands for the bot will be deleted in this channel;
* -da - all messages will be deleted in this channel;
* -ka - all messages are kept in this channel, nothing is deleted.

A channel can only be configure by an administrator.

#### Example
*!poll_channel -da*

### Create Poll

```
!poll <settings> poll_id question <response_options>
```

If no response options are provided, the default responses are Yes and No.

The poll_id is used for referring to this specific poll. It can be any string without spaces.

The first parameter that does not start with a dash is considered to be the poll_id, the next one the question and all of the following, the response options. If any of these parameters contains spaces, then they should be surrounded by quotation marks.

Available *settings* for the poll include:
* -m - each user may vote in multiple options;
* -o - each option displays only the number of votes;
* -n - users can vote in new options;
* -e - users can vote for external users;
* -y - confirm the creation of the poll. This is necessary when there's a poll with the same id or the poll limit has been reached for that server.

Settings can be combined together, using dash (-) followed by all the desired settings.

**Note:** the number of active polls per server is limited to 10. Creating a new poll when the limit has been reached will result in the deactivation of the oldest poll. To prevent this, close inactive polls manually (check **Close Poll** or **Remove Poll**).

#### Example
*!poll -n party2night "Let's party tonight?" Yes No "Only after midnight"*

![Create Poll Animation](https://raw.githubusercontent.com/correia55/PollMeBot/master/resources/create_poll.gif)

### Edit Poll

Depending on whether you want to edit the question, settings or options, you should use one of the following variants of the command:

```
!poll_edit poll_id
```

* to edit the question or settings - use the base command and add the new settings as in **Create Poll**, using dash (-), or add the new question. You cannot change both with the same command;
* to add options - use the base command and add *-add* followed by the list of options, formatted similarly to **Create Poll**;
* to remove options - use the base command and add *-rm* followed by the list of options, using their number ids separated by comma (,) and no spaces.

A poll can only be edited by its owner.

#### Examples
*!poll_edit party2night "Let's party tomorrow?"*

*!poll_edit party2night -mn*

*!poll_edit party2night -add Maybe "Only if booze"*

*!poll_edit party2night -rm 3,4*


### Close Poll

```
!poll_close poll_id selected_options
```
The selected_options are a list options separated by comma (,) and no spaces, which will be displayed in the closed poll.

A poll can only be closed by its owner.

### Remove Poll

```
!poll_remove poll_id
```

A poll can only be removed by its owner. The difference between **Close Poll** and **Remove Poll** is that remove will also delete the message associated with the poll, while close only prevents interactions with it.

#### Example
*!poll_remove party2night*


### Refresh Poll

```
!poll_refresh poll_id
```

Refreshing a poll means a new message will be created with the poll, saving you the trouble of trying to find the previous location of the poll.

#### Example
*!poll_refresh party2night*


### Vote Poll

```
!vote poll_id selected_options
```
The selected_options are a list of options separated by comma (,).

If the poll allows for new options to be created, the command followed by the new option within quotation marks (") can be used instead:
```
!vote poll_id "New option"
```

If the poll allows for external votes, to vote for an external user simply add -e followed by the voter's name within quotation marks ("), as in:
```
!vote poll_id selected_options -e "External voter's name"
```

#### Examples
*!vote party2night 3*

![Vote Poll Animation](https://raw.githubusercontent.com/correia55/PollMeBot/master/resources/vote_poll.gif)

*!vote party2night "Only if booze"*

![Vote New Option Animation](https://raw.githubusercontent.com/correia55/PollMeBot/master/resources/vote_poll_new.gif)

*!vote party2night 1 -e "My friend not on the server"*

![Vote External User Animation](https://raw.githubusercontent.com/correia55/PollMeBot/master/resources/vote_poll_external.gif)

### Unvote Poll

```
!unvote poll_id selected_option
```

Remove a vote from an option in the poll.

Similarly to **Vote Poll**, to unvote a vote from an external user add -e followed by the voter's name within quotation marks (").

#### Examples
*!unvote party2night 3*

*!unvote party2night 1 -e "My friend not on the server"*

### Help Poll

```
!help_me_poll
```

Help creates a temporary message that shows examples of basic commands.

#### Example
*!help_me_poll*

![Poll Me Help Animation](https://raw.githubusercontent.com/correia55/PollMeBot/master/resources/help_me_poll.gif)

## Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct, and the process for submitting pull requests to us.

## Author and Contributors

* **Acácio Correia**
* **[José Manteigueiro](https://github.com/jmanteigueiro)**

## License

This project is licensed under the GNU GPLv3 License - see the [LICENSE.txt](LICENSE.txt) file for details.

## Acknowledgment

Thanks for the help with suggestions on features, improvements and the README itself.
* **José Ribeiro**
* **[Vasco Lopes](https://github.com/VascoLopes)**