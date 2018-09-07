# Poll Me Bot - for Discord

A bot, for Discord, that allows you and your friends to create polls and vote.

## Available Commands

Commands start with an exclamation mark (!) followed by the command and then each 
parameter separated by a space. If a parameter contains spaces, it should be written
within quotation marks ("), otherwise it will be split into multiple parameters.

### Configure Channel

```
!poll_me_channel <setting>
```

Available *settings* for the channel configuration include:
* -dc - all messages with commands for the bot will be deleted in this channel;
* -da - all messages will be deleted in this channel;
* -ka - all messages are kept in this channel, nothing is deleted.

#### Example
!poll_me_channel -da

### Create Poll

```
!poll <settings> poll_id question <response_options>
```

If no responses are provided, the default responses are Yes and No.

The poll_id is used for referring to this specific poll. It can be any string without
 spaces.

The first parameter that does not start with a dash is considered to be the poll_id,
 the next one the question and all of the following, the response options.
If any of these parameters contains spaces, then they should be surrounded by 
quotation marks.

Available *settings* for the poll include:
* -m - each user may vote in multiple options;
* -o - each option displays only the number of votes;
* -n - users can vote in new options.

Note: the number of active polls per channel is limited to 5.

#### Example
!poll -n party2night "Let's party tonight?" Yes No "Only after midnight"

![Create Poll Animation](https://raw.githubusercontent.com/correia55/PollMeBot/master/resources/create_poll.gif)

### Edit Poll

```
!poll_edit <settings> poll_id question responses
```

A poll can only be edited by its owner.

All parameters work in the same way as in **Create Poll**, however if the number of 
options is different from the one in the poll, the new options are ignored.

#### Example
!poll_edit -n party2night "Let's party tonight at the pub?" Yes No "Only after midnight"

![Edit Poll Animation](https://raw.githubusercontent.com/correia55/PollMeBot/master/resources/edit_poll.gif)

### Remove Poll

```
!poll_remove poll_id
```

A poll can only be removed by its owner.

#### Example
!poll_remove party2night


### Refresh Poll

```
!refresh poll_id
```

Refreshing a poll means a new message will be created with the poll, saving you the 
trouble of trying to find the previous location of the poll.

#### Example
!refresh party2night

### Vote Poll

```
!vote poll_id option
```

If the poll allows for new options to be created, the command followed by the new 
option within quotation marks can be used instead:
```
!vote poll_id "New option"
```

#### Examples
!vote party2night 3

![Edit Poll Animation](https://raw.githubusercontent.com/correia55/PollMeBot/master/resources/vote_poll.gif)

!vote party2night "Only if booze"

![Edit Poll Animation](https://raw.githubusercontent.com/correia55/PollMeBot/master/resources/vote_new_poll.gif)

### Help Poll

```
!help_me_poll
```

Help creates a temporary message that shows examples of basic commands.

#### Example

!help_me_poll

![Edit Poll Animation](https://raw.githubusercontent.com/correia55/PollMeBot/master/resources/help_me_poll.gif)

## Author

**Acácio Correia**

## License

This project is licensed under the GNU GPLv3 License - see the [LICENSE.txt](LICENSE.txt) file for details.

## Acknowledgment

Thanks for the help with suggestions on features, improvements and the README itself.
* **José Ribeiro**
* **[Vasco Lopes](https://github.com/VascoLopes)**