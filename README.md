# Poll Me Bot - for Discord

A bot, for Discord, that allows you to create polls and vote.

## Available Commands

Commands start with an exclamation mark (!) followed by the command and then each parameter separated by a space, and within quotation marks (") if it contains spaces.

### Configuring Channel

```
!poll_me_channel <option>
```
configures the channel with the given option.

Available options for the channel configuration include:
* -ka - keep all messages;
* -dc - the bot will delete only messages with commands;
* -da - the bot will delete all messages that come after.

### Create Poll

```
!poll <options> poll_id question
```
creates a poll with the question and the default options (Yes and No), identified by poll_id.
The poll_id is used for refering to this specific poll and it can be any string without spaces.

The first parameter that does not start with a dash is considered the question and the following, the options.
If any of these parameters contains spaces, then they should be surrounded by quotation marks.

Available options for the poll include:
* -m - each user may vote in multiple options;
* -o - each option displays only the number of votes;
* -n - users can vote in new options.

Note: the number of active polls per channel is limited to 5.

### Edit Poll

```
!poll_edit <options> poll_id question
```
if the author of the command is the author of the poll, then edits the poll.
All parameters work in the same way as in Create Poll, however if the number of options is different from the one in the poll, the new options are ignored.

### Remove Poll

```
!poll_remove poll_id
```
if the author of the command is the author of the poll, then removes the poll.


### Refresh Poll

```
!refresh poll_id
```
creates a new message with the current poll, preventing users from having to locate the message where the poll is located.

### Vote Poll

```
!vote poll_id option
```
votes in the selected option.

If the poll allows for new options to be created you can use the command followed by the new option within quotation marks:
```
!vote poll_id "New option"
```

### Help Poll

```
!help_me_poll
```
creates a temporary message that shows examples of basic commands.

## Authors

* **Acácio Correia**

## License

This project is licensed under the GNU GPLv3 License - see the [LICENSE.txt](LICENSE.txt) file for details.
