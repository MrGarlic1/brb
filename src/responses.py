import interactions
from emoji import emojize, demojize
import json
import botdata as bd
from colorama import Fore
from dataclasses import dataclass


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
        _ = Response(rsp_dict["exact"], rsp_dict["trig"], rsp_dict["text"], rsp_dict["user_id"])
    except KeyError:
        print(Fore.YELLOW + "Invalid response found, ignoring." + Fore.RESET)
        return None
    rsp = Response(rsp_dict["exact"], rsp_dict["trig"], rsp_dict["text"], rsp_dict["user_id"])
    return rsp


def add_response(guild_id, rsp) -> bool:
    f_name: str = "responses.json" if rsp.exact else "mentions.json"
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
    except UnicodeError:
        return True
    return False


def rmv_response(guild_id: int, delete_req: Response) -> bool:

    f_name: str = "responses.json" if delete_req.exact else "mentions.json"
    try:
        with open(f"{bd.parent}/Guilds/{guild_id}/{f_name}", "r") as f:
            lines: list[dict] = json.load(f)
    except json.decoder.JSONDecodeError or FileNotFoundError:
        print(Fore.YELLOW + f"Error for {f_name} in server {guild_id}", Fore.RESET)
        return True

    # Search for desired index of response to delete. Filter by trigger, then text,
    # then exact until there is only 1 option. Return an error if nothing matches the delete request
    to_del: list = [i for i, rsp in enumerate(lines) if rsp["trig"].startswith(demojize(delete_req.trig))]

    if len(to_del) > 1:
        to_del: list = [i for i in to_del if lines[i]["text"].startswith(demojize(delete_req.text))]
    if len(to_del) > 1:
        to_del: list = [i for i in to_del if lines[i]["exact"] == delete_req.exact]
    if not to_del:
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
        f = open(file, "w")
        f.close()
        lines: list = []
    return lines


def get_resp(guild_id, trig, text, exact) -> Response | None:
    if exact:
        for rsp in bd.responses[guild_id]:
            if rsp.trig != trig:
                continue
            if not text:
                return rsp
            elif rsp.text == text:
                return rsp
    else:
        for rsp in bd.mentions[guild_id]:
            if rsp.trig != trig:
                continue
            if not text:
                return rsp
            elif rsp.text == text:
                return rsp
    return None


def gen_resp_list(guild: interactions.Guild, page: int, expired: bool) -> interactions.Embed:

    guild_id = int(guild.id)
    list_msg = interactions.Embed(
        description="*Your response list, sir.*"
    )
    guild_trigs: list = []
    for rsp in bd.responses[guild_id]:
        guild_trigs.append(rsp)
    for mtn in bd.mentions[guild_id]:
        guild_trigs.append(mtn)

    max_pages: int = 1 if len(guild_trigs) <= 10 else len(guild_trigs) // 10 + 1  # Determine max pg @ 10 entries per pg
    page: int = 1 + (page % max_pages)  # Loop back through pages both ways
    footer_end: str = " | This message is inactive." if expired else " | This message deactivates after 5 minutes."
    list_msg.set_author(name=guild.name, icon_url=bd.bot_avatar_url)
    list_msg.set_thumbnail(url=guild.icon.url)
    list_msg.set_footer(text=f"Page {page}/{max_pages} {footer_end}")
    nums: range = range((page-1)*10, len(guild_trigs)) if page == max_pages else range((page-1)*10, page*10)
    for i in nums:
        pref: str = "**Exact Trigger:** " if guild_trigs[i].exact else "**Phrase Trigger:** "
        rsp_field: str = f"{pref}{guild_trigs[i].trig} \n **Respond: ** {guild_trigs[i].text}"
        if len(rsp_field) >= 1024:
            rsp_field: str = f"{pref}{guild_trigs[i].trig} \n **Respond: ** *[Really, really, really long response]*"

        list_msg.add_field(
            name="\u200b",
            value=rsp_field, inline=False
        )
    return list_msg
