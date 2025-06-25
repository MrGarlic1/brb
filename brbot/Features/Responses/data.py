from emoji import emojize, demojize
import json
import brbot.Core.botdata as bd
from brbot.Shared.buttons import PrevPgButton, NextPgButton
import logging
from discord.ui import View
from discord import Interaction, Guild, Embed, Message
from random import choice

logger = logging.getLogger(__name__)


class Response:
    def __init__(self, exact: bool, trig: str, text: str, user_id: int = 0):
        self.exact = exact
        self.trig = trig
        self.text = text
        self.user_id = user_id

    def add_rsp_text(self, new_text):
        if not isinstance(self.text, list):
            self.text = list(self.text)
        self.text.append(new_text)

    def __repr__(self):
        return f"Trigger: {self.trig}, Text: {self.text}, Exact: {self.exact},  User ID: {self.user_id}"


def dict_to_rsp(rsp_dict: dict) -> Response | None:
    if not rsp_dict:
        return None
    try:
        _ = Response(
            rsp_dict["exact"], rsp_dict["trig"], rsp_dict["text"], rsp_dict["user_id"]
        )
    except KeyError:
        logger.warning("Invalid response found, ignoring.")
        return None
    rsp = Response(
        rsp_dict["exact"], rsp_dict["trig"], rsp_dict["text"], rsp_dict["user_id"]
    )
    return rsp


def add_response(guild_id: int, rsp: Response) -> bool:
    f_name: str = "responses.json"
    rsp.trig, rsp.text = demojize(rsp.trig), demojize(rsp.text)
    if not rsp.text:
        return True
    try:
        with open(f"{bd.parent}/Guilds/{guild_id}/{f_name}", "r") as f:
            try:
                lines: list = json.load(f)
            except json.decoder.JSONDecodeError:
                lines: list = []
        duplicates = [next((x for x in lines if x["trig"] == rsp.trig), None)]
        if duplicates != [None]:
            for x in duplicates:
                if x["text"] == rsp.text:  # Reject identical additions
                    return True
        lines.append(rsp.__dict__)
    except FileNotFoundError:
        f = open(f"{bd.parent}/Guilds/{guild_id}/{f_name}", "w")
        f.close()
    try:
        with open(f"{bd.parent}/Guilds/{guild_id}/{f_name}", "w") as f:
            json.dump(lines, f, indent=4)
    except UnicodeError as e:
        logger.error(f"Could not write to {f_name}: {e}")
        return True
    return False


def rmv_response(guild_id: int, delete_req: Response) -> bool:
    f_name: str = "responses.json"
    try:
        with open(f"{bd.parent}/Guilds/{guild_id}/{f_name}", "r") as f:
            lines: list[dict] = json.load(f)
    except json.decoder.JSONDecodeError or FileNotFoundError as e:
        logger.warning(f"Error in response file {f_name} in server {guild_id}: {e}")
        return True

    # Search for desired index of response to delete. Filter by trigger, then text,
    # then exact until there is only 1 option. Return an error if nothing matches the delete request
    to_del: list = [
        i for i, rsp in enumerate(lines) if rsp["trig"] == demojize(delete_req.trig)
    ]
    if len(to_del) > 1:
        to_del: list = [
            i for i in to_del if lines[i]["text"] == demojize(delete_req.text)
        ]
    if len(to_del) > 1:
        to_del: list = [i for i in to_del if lines[i]["exact"] == delete_req.exact]
    if not to_del or len(to_del) > 1:
        return True

    lines.pop(to_del[0])

    with open(f"{bd.parent}/Guilds/{guild_id}/{f_name}", "w") as f:
        if not lines:
            f.write("[]")
        else:
            json.dump(lines, f, indent=4)

    return False


def load_responses(file) -> list:
    try:
        with open(file, "r") as f:
            try:
                lines: list = json.load(f)
            except ValueError:
                lines: list = []
        for idx, line in enumerate(lines):
            lines[idx] = dict_to_rsp(line)
        for rsp in lines:
            rsp.trig = emojize(rsp.trig)
            rsp.text = emojize(rsp.text)

    except FileNotFoundError:
        logger.warning(f"Error loading response file {file}, blank file created")
        f = open(file, "w")
        f.close()
        lines: list = []
    return lines


def get_resp(
    guild_id: int, trig: str, text: str = "", exact: bool = None
) -> Response | None:
    for rsp in bd.responses[guild_id]:
        if rsp.trig == trig:
            if rsp.text == text or not text:
                if rsp.exact == exact or exact is None:
                    return rsp
    return None


def gen_resp_list(guild: Guild, page: int) -> Embed:
    guild_id = int(guild.id)
    list_msg = Embed(description="*Your response list, sir.*")

    # Determine max pg @ 10 entries per pg
    max_pages: int = (
        1
        if len(bd.responses[guild_id]) <= 10
        else len(bd.responses[guild_id]) // 10 + 1
    )
    page: int = 1 + ((page - 1) % max_pages)  # Loop back through pages both ways
    list_msg.set_author(name=guild.name, icon_url=bd.bot_avatar_url)
    list_msg.set_thumbnail(url=guild.icon.url)
    list_msg.set_footer(text=f"Page {page}/{max_pages}")
    nums: range = (
        range((page - 1) * 10, len(bd.responses[guild_id]))
        if page == max_pages
        else range((page - 1) * 10, page * 10)
    )
    for i in nums:
        pref: str = (
            "**Exact Trigger:** "
            if bd.responses[guild_id][i].exact
            else "**Phrase Trigger:** "
        )
        rsp_field: str = f"{pref}{bd.responses[guild_id][i].trig} \n **Respond: ** {bd.responses[guild_id][i].text}"
        if len(rsp_field) >= 1024:
            logger.debug(f"Response too long: {rsp_field}, showing shortened version")
            rsp_field: str = (
                f"{pref}{bd.responses[guild_id][i].trig} \n "
                f"**Respond: ** *[Really, really, really long response]*"
            )

        list_msg.add_field(name="\u200b", value=rsp_field, inline=False)
    return list_msg


def generate_response(message: Message) -> str | None:
    if message.author.bot:
        return None
    channel = message.channel
    if channel.type == 1:  # Ignore DMs
        return None

    guild_id = message.guild.id

    to_send = [
        response.text
        for response in bd.responses[guild_id]
        if response.trig == message.content.lower() and response.exact
    ]
    logger.debug(f"Exact response match found, 1/{len(to_send)} possible responses")
    if to_send:
        return choice(to_send)

    if not bd.config[guild_id]["ALLOW_PHRASES"]:
        return None

    to_send = [
        response.text
        for response in bd.responses[guild_id]
        if response.trig in message.content.lower() and not response.exact
    ]
    logger.debug(f"Phrase response match found, 1/{len(to_send)} possible responses")
    if to_send:
        return choice(to_send)

    return None


class RspView(View):
    """
    Discord UI View for handling response view interactions.

    Attributes:
        page (int): Which response page in server's response list to display
    """

    def __init__(self, page: int):
        super().__init__(timeout=60)
        self.add_item(PrevPgButton())
        self.add_item(NextPgButton())
        self.page = page

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.data["custom_id"] == "prev_page":
            self.page -= 1

        elif interaction.data["custom_id"] == "next_page":
            self.page += 1

        embed = gen_resp_list(interaction.guild, self.page)

        await interaction.response.edit_message(embed=embed, view=self)
        return False
