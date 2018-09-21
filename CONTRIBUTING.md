# Contributing

When contributing to this repository, please first discuss the changes you wish to make, via issue, with the owners of this repository before making a change.

## Testing

1. Go to [Discord's Developer Portal](https://discordapp.com/developers/applications/) and create a new application. Change the name of the application and then go to the Bot tab and click the **Add Bot** button, confirming with the **Yes, do it!** button. You will need two data fields from this page: the bot's Token and the Client ID;
2. You will need a server in Discord to test out the bot. To add it to your test server go to [Discord Permissions Calculator](https://discordapi.com/permissions.html), select the permissions: *Read Messages*, *Send Messages* and *Manage Messages*; then paste the Client ID and use the link below;
3. Install and configure PostgreSQL in your system;
4. Create two environment variables in your system: *BOT_TOKEN* containing the token to the bot application; and *DATABASE_URL* the url used to connect to the PostgreSQL database.
5. When running the bot, it should now appear online in your test server and you can now test things before requesting a pull.

## Pull Request Process

1. Ensure all needed dependencies are present at the **requirements.txt**;
2. Update the **README.md** with details of changes, including example gifs for new features. (See the existing gifs to make sure you follow a similar approach to the recording of the ones you are adding, and place them in the resources folder);
3. Make sure you have tested all changes you have made before doing the pull request, including existing features that may have been affected by your changes.

