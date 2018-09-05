# Poll Me Bot - for Discord

A bot, for Discord, that allows you to create polls and vote.

## Available Commands

Commands start with an exclamation mark (!) followed by the command and then each parameter separated by a space, and within quotation marks (") if it contains spaces.

### Configuring Channel

```
!poll_me_channel <setting>
```
configures the channel with the given setting.

Available settings for the channel configuration include:
* -ka - keep all messages;
* -dc - the bot will delete only messages with commands;
* -da - the bot will delete all messages that come after.

#### Example: !poll_me_channel -da

### Create Poll

```
!poll <settings> poll_id question <response_options>
```
creates a poll with the question and the responses provided, identified by poll_id.
If no responses are provided, the default responses are Yes and No.
The poll_id is used for refering to this specific poll and it can be any string without spaces.

The first parameter that does not start with a dash is considered to be the poll_id, then the question and all of the following, the response options.
If any of these parameters contains spaces, then they should be surrounded by quotation marks.

Available settings for the poll include:
* -m - each user may vote in multiple options;
* -o - each option displays only the number of votes;
* -n - users can vote in new options.

#### Example: !poll -n party2night "Party tonight on the alley?" Yes No "Maybe if chicks"

Note: the number of active polls per channel is limited to 5.

### Edit Poll

```
!poll_edit <settings> poll_id question responses
```
if the author of the command is the author of the poll, then edits the poll.
All parameters work in the same way as in Create Poll, however if the number of options is different from the one in the poll, the new options are ignored.

#### Example: !poll_edit -n party2night "Party tonight on the alley at 9PM?" Yes No "Maybe if chicks"

### Remove Poll

```
!poll_remove poll_id
```
if the author of the command is the author of the poll, then removes the poll.

#### Example: !poll_remove party2night


### Refresh Poll

```
!refresh poll_id
```
creates a new message with the current poll, preventing users from having to locate the message where the poll is located.

#### Example: !refresh party2night

### Vote Poll

```
!vote poll_id option
```
votes in the selected option.

If the poll allows for new options to be created, you can use the command followed by the new option within quotation marks:
```
!vote poll_id "New option"
```

#### Example: !vote party2night 3
#### Example: !vote party2night "Only if booze"

### Help Poll

```
!help_me_poll
```
creates a temporary message that shows examples of basic commands.

## Authors

* **Acácio Correia**

## License

This project is licensed under the GNU GPLv3 License - see the [LICENSE.txt](LICENSE.txt) file for details.
