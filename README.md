# brb
Response bot for discord, now with trains!

## Features
- Add a trigger phrase and response text that the bot will automatically respond to (can specify if the message has to exactly match or just contain the trigger phrase)
- Remove and list existing responses
- Permission configuration options
  - Max responses per user
  - Set response delete permissions to user-specific or global
  - Allow/disallow phrase responses
- ### Anime trains game (rules to be listed)
  - Automatic scoring [IN PROGRESS]
  - Randomly generated setup for the board
  - Configurable size/players
  - Fully playable through discord/anilist

## Commands
- /listresponses
- /trains [newgame/board/stats/shot/undo]
- /train rules
- /response [add/remove]
- /mod [add/remove/deleteRspData/deletetrain/restoretrain]
- /config [allowphrases/limitresponses/userperms/view/reset]

## Installation
### MacOS/Linux
1. Download appropriate release package
2. Set your discord token in .env
3. Run autorun.command/autorun.sh

### Windows
1. Download appropriate release package
2. Set your discord token in .env
3. Run main.exe

### Build from source
1. Clone repo: `git clone https://github.com/MrGarlic1/Brb`
2. Change dir: `cd Brb`
3. Create and activate venv: `python -m venv venv` `source ./venv/bin/activate`
4. Install requirements: `pip install -r requirements.txt`
5. Edit .env file with bot token token
6. Run bot: `python src/main.py`
