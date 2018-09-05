# Poll Me Bot - for Discord

A bot, for Discord, that allows you to create polls and vote.

## Available Commands

Commands start with an exclamation mark (!) followed by the command and then each parameter separated by a space, and within quotation marks (") if it contains spaces.

### Creating Poll

```
!poll Question
```
creates a poll with the question and the default options (Yes and No).

The first parameter that does not start with a dash is considered the question and the following, the options.
If any of these parameters contains spaces, then they should be surrounded by quotation marks.

Available options for the poll include:
* -m - each user may vote in multiple options;
* -o - each option displays only the number of votes;
* -n - users can vote in new options;
* -dc - the bot will delete all messages with the commands;
* -da - the bot will delete all messages that come after.

### Refresh Poll

```
!refresh
```
creates a new message with the current poll, preventing users from having to locate the message where the poll is located.

### Vote Poll

```
!vote option
```
votes in the selected option.

If the poll allows for new options to be created you can use the command followed by the new option within quotation marks:
```
!vote "New option"
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
