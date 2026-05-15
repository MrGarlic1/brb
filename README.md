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
- TBD: Scoring

### Animanga

- Link discord profile to anilist
- Generate personalized manga/anime recommendations
- Daily animanga activity leaderboards per server
- Configuration options
  - Set channel to send leaderboard

### Catgirl Gacha

- Roll a random image of a catgirl. That's it. Seriously.
- Configuration options
  - Enable/Disable NSFW content

## Commands

- /response
  - `add [trigger] [response] <exact>`
  - `list <page>`
  - `remove [trigger] <response> <exact>`
  - `clearall` (Admin Only)
- /trains
  - `board`
  - `buy [item]`
  - `inventory`
  - `newgame [name] [players] <width> <height>`
  - `rules <page>`
  - `shot [row] [column] [link] [info]`
  - `stats <name>`
  - `undo`
  - `delete <keep_files>` (Admin Only)
  - `restore [name]` (Admin Only)
- /config (Admin Only)
  - `set [setting] [value]`
  - `view`
  - `wipe`
- /animanga
  - `link [username]`
  - `recommend <genre> <medium> <force>`
  - `track_daily`
  - `untrack_daily`
- /neko
  - `pic`
- /help
- /about

### Build from source

1. Clone repo: `git clone https://github.com/MrGarlic1/Brb`
2. Change dir: `cd Brb`
3. Create and activate venv: `python -m venv venv; source ./venv/bin/activate`
4. Install requirements: `pip install -r requirements.txt`
5. Edit .env file with bot token
6. Run bot: `python main.py`

> [!note]
> This project makes a best‑effort attempt to respect artist licenses and permissions.
> Images without explicit permissive licenses may be removed upon request.
> If you are the rights holder, please contact us and affected content will be removed promptly.
