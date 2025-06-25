# brb
Response bot for discord, now with trains!

## Features
### Responses
- Add a trigger phrase and response text that the bot will automatically respond to (can specify if the message has to exactly match or just contain the trigger phrase)
- Remove and list existing responses
- Permission configuration options
  - Max responses per user
  - Set response delete permissions to user-specific or global
  - Allow/disallow phrase responses
### Anime trains game
  - Automatic scoring
  - Randomly generated setup for the board
  - Configurable size/players
  - Fully playable through discord/anilist
### Anime bingo game (BETA)
  - Randomly generated bingo boards
  - View your/other player's boards
  - Fully playable through discord
  - TBD: Scoring, stats
### Animanga
  - Link discord profile to anilist
  - Generate personalized manga/anime recommendations

## Commands
- /response
  - add [trigger] [response] <exact>
  - list <page>
  - remove [trigger] <response> <exact>
  - clearall (Admin Only)
- /trains
  - board
  - buy [item]
  - inventory
  - newgame [name] [players] <width> <height>
  - rules <page>
  - shot [row] [column] [link] [info]
  - stats <name>
  - undo
  - delete <keep_files> (Admin Only)
  - restore [name] (Admin Only)
- /config [allowphrases/limitresponses/userperms/view/reset]
  - set [setting] [value]
- /animanga
  - link [username]
  - recommend <genre> <medium> <force>

### Build from source
1. Clone repo: `git clone https://github.com/MrGarlic1/Brb`
2. Change dir: `cd Brb`
3. Create and activate venv: `python -m venv venv; source ./venv/bin/activate`
4. Install requirements: `pip install -r requirements.txt`
5. Edit .env file with bot token
6. Run bot: `python main.py`
