# Bot functions
# Version 3.0
# Ben Samans, Updated 11/2/2023

import interactions
from emoji import emojize, demojize
import json
import botdata as bd
from time import strftime
from termcolor import colored
from colorama import init
import yaml
import asyncio
from os import path, mkdir

init()


class Response:
    def __init__(self, exact, trig, text, user_id):
        self.exact = exact
        self.trig = trig
        self.text = text
        self.user_id = user_id

    def __repr__(self):
        return f'<Exact={self.exact}> <Trig={self.trig}> <Text={self.text}> <User_id={self.user_id}>'

    def asdict(self):
        return {'exact': self.exact, 'trig': self.trig, 'text': self.text, 'user_id': self.user_id}

    def add_rsp_text(self, new_text):
        if not isinstance(self.text, list):
            self.text = list(self.text)
        self.text.append(new_text)


class ListMsg:
    def __init__(self, num, page, guild, channel):
        self.num = num
        self.page = page
        self.guild = guild
        self.channel = channel


def dict_to_rsp(rsp_dict: dict):
    if not rsp_dict:
        return None
    try:
        rsp = Response(rsp_dict['exact'], rsp_dict['trig'], rsp_dict['text'], rsp_dict['user_id'])
    except KeyError:
        if rsp_dict['m']:
            rsp_dict['exact'] = False
        else:
            rsp_dict['exact'] = True
        rsp_dict.pop('m')
        rsp = Response(rsp_dict['exact'], rsp_dict['trig'], rsp_dict['text'], rsp_dict['user_id'])
    return rsp


def add_response(guild_id, rsp):
    f_name = 'responses.txt' if rsp.exact else 'mentions.txt'
    rsp.trig, rsp.text = demojize(rsp.trig), demojize(rsp.text)
    if not rsp.text:
        print('error1')
        return True
    try:
        with open(f'{bd.parent}/Guilds/{guild_id}/{f_name}', 'r') as f:
            try:
                lines = json.load(f)
            except json.decoder.JSONDecodeError:
                lines = []
        duplicates = [next((x for x in lines if x['trig'] == rsp.trig), None)]
        if duplicates != [None]:
            for x in duplicates:
                if x['text'] == rsp.text:  # Reject identical additions
                    print('error2')
                    return True
        lines.append(rsp.asdict())
    except FileNotFoundError:
        f = open(f'{bd.parent}/Guilds/{guild_id}/{f_name}', 'w')
        f.close()
    try:
        with open(f'{bd.parent}/Guilds/{guild_id}/{f_name}', 'w') as f:
            json.dump(lines, f, indent=4)
    except UnicodeError:
        return True


def rmv_response(guild_id, rsp):
    f_name = 'responses.txt' if rsp.exact else 'mentions.txt'
    try:
        with open(f'{bd.parent}/Guilds/{guild_id}/{f_name}', 'r') as f:
            try:
                lines = json.load(f)
            except json.decoder.JSONDecodeError:
                print('error1')
                return True
        to_del = [i for i, x in enumerate(lines) if x['trig'] == demojize(rsp.trig)]  # All matching entries
        if len(to_del) > 1:
            to_del = [
                i for i, x in enumerate(lines) if
                x['trig'] == demojize(rsp.trig) and x['text'].lower() == demojize(rsp.text.lower())
            ]
        if not to_del:
            print('error2')
            return True
        k = 0
        for i in to_del:
            lines.pop(i - k)
            k += 1
        with open(f'{bd.parent}/Guilds/{guild_id}/{f_name}', 'w') as f:
            if not lines:
                f.write('[]')
            else:
                json.dump(lines, f, indent=4)

    except FileNotFoundError or ValueError:
        return True


def load_responses(file):
    lines = []
    try:
        with open(file, 'r') as f:
            try:
                lines = json.load(f)
            except ValueError:
                lines = []
        for idx, line in enumerate(lines):
            lines[idx] = dict_to_rsp(line)
        for rsp in lines:
            rsp.trig = emojize(rsp.trig)
            rsp.text = emojize(rsp.text)
    except FileNotFoundError:
        f = open(file, 'w')
        f.close()
    return lines


def get_resp(guild_id, trig, text, exact):
    if exact:
        for rsp in bd.responses[guild_id]:
            if rsp.trig == trig:
                if not text:
                    return rsp
                if rsp.text == text:
                    return rsp
    else:
        for rsp in bd.mentions[guild_id]:
            if rsp.trig == trig:
                if not text:
                    return rsp
                if rsp.text == text:
                    return rsp


def load_config(guild):
    # Load and validate guild bd.configs
    try:
        bd.config[int(guild.id)] = yaml.load(
            open(f'{bd.parent}/Guilds/{str(guild.id)}/config.yaml'),
            Loader=yaml.Loader
        )

        # Add missing keys
        for key in bd.default_config.keys():
            if key not in bd.config[int(guild.id)].keys():
                bd.config[int(guild.id)][key] = bd.default_config[key]
                print(
                    colored(f'{strftime("%Y-%m-%d %H:%M:%S")} :  ', 'white') +
                    colored(f'Config file for {guild.name} missing {key}, set to default.', 'yellow')
                )
                with open(f'{bd.parent}/Guilds/{int(guild.id)}/config.yaml', 'w') as f:
                    yaml.dump(bd.config[int(guild.id)], f, Dumper=yaml.Dumper)

        # Remove invalid keys
        temp = dict(bd.config[int(guild.id)])
        for key in bd.config[int(guild.id)].keys():
            if key not in bd.default_config.keys():
                temp = dict(bd.config[int(guild.id)])
                del temp[key]
                print(
                    colored(f'{strftime("%Y-%m-%d %H:%M:%S")} :  ', 'white') +
                    colored(f'Invalid key {key} in {guild.name} config, removed.', 'yellow')
                )
                with open(f'{bd.parent}/Guilds/{int(guild.id)}/config.yaml', 'w') as f:
                    yaml.dump(temp, f, Dumper=yaml.Dumper)
        bd.config[int(guild.id)] = temp

    # Create new file if config is missing
    except FileNotFoundError:
        with open(f'{bd.parent}/Guilds/{int(guild.id)}/config.yaml', 'w') as f:
            yaml.dump(bd.default_config, f, Dumper=yaml.Dumper)
        print(
            colored(f'{strftime("%Y-%m-%d %H:%M:%S")} :  ', 'white') +
            colored(f'No config file found for {guild.name}, created default config file.', 'yellow')
        )
        bd.config[int(guild.id)] = yaml.load(open(f'{bd.parent}/Guilds/{guild.id}/config.yaml'), Loader=yaml.Loader)


def guild_add(guild):
    guild_id = str(guild.id)
    if not path.exists(f'{bd.parent}/Guilds/{guild_id}'):
        mkdir(f'{bd.parent}/Guilds/{guild_id}')
        print(
            colored(f'{strftime("%Y-%m-%d %H:%M:%S")} :  ', 'white') +
            colored(f'Guild folder for guild {guild.id} created successfully.', 'green')
        )
        with open(f'{bd.parent}/Guilds/{int(guild.id)}/config.yaml', 'w') as f:
            yaml.dump(bd.default_config, f, Dumper=yaml.Dumper)
        bd.config[int(guild.id)] = bd.default_config
        bd.responses[int(guild_id)] = []
        bd.mentions[int(guild_id)] = []


def gen_resp_list(guild, page, expired):

    guild_id = int(guild.id)
    list_msg = interactions.Embed(
        description='*Your response list, sir.*'
    )
    guild_trigs = []
    for rsp in bd.responses[guild_id]:
        guild_trigs.append(rsp)
    for mtn in bd.mentions[guild_id]:
        guild_trigs.append(mtn)

    max_pages = 1 if len(guild_trigs) <= 10 else len(guild_trigs) // 10 + 1  # Determine max pg at 10 entries per pg
    page = 1 + (page % max_pages)  # Loop back through pages both ways
    footer_end = ' | This message is inactive.' if expired else ' | This message deactivates after 5 minutes.'
    list_msg.set_author(name=guild.name, icon_url=bd.bot_avatar_url)
    list_msg.set_thumbnail(url=guild.icon.url)
    list_msg.set_footer(text=f'Page {page}/{max_pages} {footer_end}')
    nums = range((page-1)*10, len(guild_trigs)) if page == max_pages else range((page-1)*10, page*10)
    for i in nums:
        pref = '**Exact Trigger:** ' if guild_trigs[i].exact else '**Phrase Trigger:** '
        rsp_field = f'{pref}{guild_trigs[i].trig} \n **Respond:** {guild_trigs[i].text}'
        if len(rsp_field) >= 1024:
            rsp_field = f'{pref}{guild_trigs[i].trig} \n **Respond:** *[Really, really, really long response]*'

        list_msg.add_field(
            name='\u200b',
            value=rsp_field, inline=False
        )
    return list_msg


async def close_msg(list_msg, delay, ctx, msg):
    await asyncio.sleep(delay)
    await msg.edit(embeds=gen_resp_list(ctx.guild, list_msg.page, True))
    bd.active_msgs.remove(list_msg)


"""
if "rempowerbed" in message.content:
    await channel.send(
        content='Wished by <@493498108211232779>',
        embeds=bu.power_embed(),
        components=bu.wish_button()
    )
    await channel.send(
        content='Wished by <@302266697488924672>',
        embeds=bu.rembed(),
        components=bu.wish_button()
    )
        
def rembed():
    embed = interactions.Embed(
    )
    embed.color = 0xff9c2c
    embed.add_field(
        name='Rem',
        inline=False,
        value='\u200b\nRe:Zero kara Hajimeru Isekai Seikatsu\n'
              '**1528** <:Kakera:1103395628723228732>\n'
              'React with any emoji to claim!',
    )
    embed.set_image(url='https://mudae.net/uploads/4190198/-00NfGVxGabXCbZZfHPc~bFtvJih.png')
    return embed


def power_embed():
    embed = interactions.Embed(
    )
    embed.color = 0xff9c2c
    embed.add_field(
        name='Power',
        inline=False,
        value='\u200b\nChainsaw Man\n'
              '**1364** <:Kakera:1103395628723228732>\n'
              'React with any emoji to claim!',
    )
    embed.set_image(url='https://mudae.net/uploads/7637289/JW6Pl0JPh04sSEnVARM3~qcyFORS.png')
    return embed
"""


def wish_button():
    return interactions.Button(
        style=interactions.ButtonStyle.SECONDARY,
        label='💕',
        custom_id='wish'
    )


def prevpg_button():
    return interactions.Button(
        style=interactions.ButtonStyle.SECONDARY,
        label="←",
        custom_id="prev page",
    )


def nextpg_button():
    return interactions.Button(
        style=interactions.ButtonStyle.SECONDARY,
        label="→️",
        custom_id="next page",
    )
