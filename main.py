"""
Bootleg Response Bot
Mr.Garlic
Last Updated: 01/05/2022
"""

from os import environ, path, mkdir
import discord
from dotenv import load_dotenv
from termcolor import colored
from time import strftime
from colorama import init
from botutils import process_args, is_command
from emoji import emojize, demojize
from random import choice
import asyncio
init()

load_dotenv()
del_delay = 5
bot_id = 887530423826145310
prefix = 'brbot'
responses, mentions = {}, {}
active_msgs = []
intents = discord.Intents.default()
intents.typing = False
intents.invites = False
intents.voice_states = False
client = discord.Client(intents=intents)


class Response:
    def __init__(self, m, trig, text):
        self.m = m
        self.trig = trig
        self.text = text

    def __repr__(self):
        return f'<Mention={self.m}> <Trig={self.trig}> <Text={self.text}>'


class ListMsg:
    def __init__(self, num, page, guild):
        self.num = num
        self.page = page
        self.guild = guild


def guild_add(guild):
    guild_id = str(guild.id)
    if not path.exists(f'Guilds/{guild_id}'):
        mkdir(f'Guilds/{guild_id}')
        print(
            colored(f'{strftime("%Y-%m-%d %H:%M:%S")} :  ', 'white') +
            colored(f'Guild folder for guild {guild.id} created successfully.', 'green')
        )
    responses[int(guild_id)] = []
    mentions[int(guild_id)] = []


def add_response(guild, rsp):
    f_name = 'mentions.txt' if rsp.m else 'responses.txt'
    rsp.trig, rsp.text = demojize(rsp.trig), demojize(rsp.text)
    if not rsp.text:
        return True
    try:
        with open(f'Guilds/{guild.id}/{f_name}', 'r') as f:
            lines = [i.strip('\n') for i in f.readlines()]
            if rsp.trig in lines:  # Trigger already exists
                idx = [i for i, x in enumerate(lines) if x == rsp.trig]
                for i in idx:
                    if lines[i + 1] == rsp.text:  # Reject identical additions
                        return True

    except FileNotFoundError:
        f = open(f'Guilds/{guild.id}/{f_name}', 'w')
        f.close()
    try:
        with open(f'Guilds/{guild.id}/{f_name}', 'a') as f:
            rsp.trig.replace('\n', '')
            rsp.text.replace('\n', '')
            f.write(f'{rsp.trig.lower()}\n{rsp.text}\n')
            return False
    except UnicodeError:
        return True


def rmv_response(guild, rsp):
    f_name = 'mentions.txt' if rsp.m else 'responses.txt'

    try:
        with open(f'Guilds/{guild.id}/{f_name}', 'r') as f:
            lines = f.readlines()
            to_del = [i for i, x in enumerate(lines[0::2]) if x == demojize(rsp.trig) + '\n']
            k = 0
            for i in to_del:
                lines.pop(i - k + 1)
                lines.pop(i - k)
                k += 2
        with open(f'Guilds/{guild.id}/{f_name}', 'w') as f:
            f.writelines(lines)
        return False

    except FileNotFoundError or ValueError:
        return True


def load_responses(file, is_m):
    resp = []
    try:  # Load & read mention triggers
        with open(file, 'r') as f:
            lines = f.readlines()
            lines = [i.strip('\n') for i in lines]
            for i in range(0, len(lines), 2):
                resp.append(Response(is_m, emojize(lines[i]), emojize(lines[i+1])))
    except FileNotFoundError:
        f = open(file, 'w')
        f.close()
    return resp


def gen_resp_list(guild, page, expired):
    list_msg = discord.Embed(
        description='Your response list, sir.'
    )
    guild_trigs = []
    for rsp in responses[guild.id]:
        guild_trigs.append(rsp)
    for mtn in mentions[guild.id]:
        guild_trigs.append(mtn)

    max_pages = len(guild_trigs) // 10 + 1
    page = 1 + (page % max_pages)  # Loop back through pages both ways

    footer_end = ' | This message is inactive.' if expired else ' | This message deactivates after 5 minutes.'
    list_msg.set_author(name=guild.name, icon_url=guild.icon_url)
    list_msg.set_footer(text=f'Page {page}/{max_pages} {footer_end}')
    nums = range((page-1)*10, len(guild_trigs)) if page == max_pages else range((page-1)*10, page*10)

    for i in nums:
        pref = '**Mention:** ' if guild_trigs[i].m else '**Say:** '
        rsp_field = f'{pref}{guild_trigs[i].trig} \n **Respond:** {guild_trigs[i].text}'
        if len(rsp_field) >= 1024:
            rsp_field = f'{pref}{guild_trigs[i].trig} \n **Respond:** *[Really, really, really long response]*'

        list_msg.add_field(
            name='\u200b',
            value=rsp_field, inline=False
        )
    return list_msg


async def close_msg(list_msg, delay, channel, guild):
    await asyncio.sleep(delay)
    message = await channel.fetch_message(list_msg.num)
    await message.edit(embed=gen_resp_list(guild, list_msg.page, True))
    active_msgs.remove(list_msg)


async def update_msg(payload):
    payload.emoji = str(payload.emoji)
    if payload.emoji not in ('⬅️', '➡️') or payload.user_id == bot_id:
        return True
    for msg in active_msgs:
        if payload.message_id == msg.num:
            if payload.emoji == '⬅️':
                page = msg.page - 1
                msg.page -= 1
            elif payload.emoji == '➡️':
                page = msg.page + 1
                msg.page += 1
            else:
                break
            channel = discord.utils.get(client.private_channels, id=payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            await message.edit(embed=gen_resp_list(msg.guild, page, False))
            break


@client.event
async def on_message(message):
    if isinstance(message.channel, discord.channel.DMChannel):  # Ignore DMs
        return False
    guild = message.channel.guild

    if not is_command(message, prefix):  # Any normal message
        if not message.author.bot:
            to_send = []
            done = False
            for i in responses[guild.id]:
                if i.trig == message.content.lower():
                    to_send.append(i.text)
                    done = True
            if done:
                to_send = choice(to_send) if len(to_send) > 1 else to_send[0]
                await message.channel.send(to_send)
                return False

            for i in mentions[guild.id]:
                if i.trig in message.content.lower():
                    to_send.append(i.text)
                    done = True
            if done:
                to_send = choice(to_send) if len(to_send) > 1 else to_send[0]
                await message.channel.send(to_send)
        return False

    print(colored(strftime("%Y-%m-%d %H:%M:%S") + ' :  ', 'white') + f'{message.author}: {message.content}')

    if message.content.lower() == 'brbot list responses':
        resp_msg = await message.author.send(embed=gen_resp_list(guild, 0, False))
        await resp_msg.add_reaction('⬅️')
        await resp_msg.add_reaction('➡️')
        sent = ListMsg(resp_msg.id, 0, guild)
        active_msgs.append(sent)
        asyncio.create_task(
            close_msg(sent, 300, resp_msg.channel, guild)
        )
        return False

    if message.content.lower() == 'brbot delete all data' and \
            message.author.permissions_in(message.channel).administrator:
        open(f'Guilds/{guild.id}/responses.txt', 'w')
        f = open(f'Guilds/{guild.id}/mentions.txt', 'w')
        f.close()
        responses[guild.id], mentions[guild.id] = [], []
        await message.add_reaction('✅')
        return False

    try:
        message_list = message.content.split(' ')  # Splits command into command and arguments
        cmd = message_list[3].lower()
        args = process_args(message_list[4:])
    except IndexError:  # weird cases with the prefix but without a proper command
        return True

    if cmd in ('say', 'mention'):
        if cmd == 'say':
            is_m, f_name = False, 'responses.txt'
        else:
            is_m, f_name = True, 'mentions.txt'

        if args[1].lower() in ('don\'t', 'dont'):
            for i, arg in enumerate(args[1:4], 1):
                args[i] = arg.lower()
            if args[1:4] == ['don\'t', 'say', 'anything'] or args[1:4] == ['dont', 'say', 'anything']:
                error = rmv_response(guild, Response(is_m, args[0].lower(), '_'))
                if not error:
                    await message.add_reaction('✅')
                else:
                    await message.add_reaction('❌')

        elif args[1].lower() == 'you':
            for i, arg in enumerate(args[1:3], 1):
                args[i] = arg.lower()
            if args[1:3] == ['you', 'say']:
                error = add_response(guild, Response(is_m, args[0].lower(), ' '.join(args[3:])))
                if not error:
                    await message.add_reaction('✅')
                else:
                    await message.add_reaction('❌')
        if cmd == 'say':
            responses[guild.id] = load_responses(f'Guilds/{guild.id}/{f_name}', is_m)
        else:
            mentions[guild.id] = load_responses(f'Guilds/{guild.id}/{f_name}', is_m)
        return False


@client.event
async def on_guild_join(guild):
    guild_add(guild)
    print(
        colored(f'{strftime("%Y-%m-%d %H:%M:%S")} :  ', 'white') + f'Added to guild {guild.id}.'
    )


@client.event
async def on_ready():
    print(colored(strftime("%Y-%m-%d %H:%M:%S") + ' :  ', 'white') + f'{client.user} has connected to Discord!')
    guilds = client.guilds
    assert guilds, 'Error connecting to Discord, no guilds listed.'
    print(
        colored(strftime("%Y-%m-%d %H:%M:%S") + ' :  ', 'white') + 'Connected to the following guilds: ' +
        colored(', '.join(guild.name for guild in guilds), 'cyan')
    )
    for guild in guilds:
        mentions[guild.id] = load_responses(f'Guilds/{guild.id}/mentions.txt', True)
        responses[guild.id] = load_responses(f'Guilds/{guild.id}/responses.txt', False)
        print(
            colored(f'{strftime("%Y-%m-%d %H:%M:%S")} :  ', 'white') +
            colored(f'Responses loaded for {guild.name}', 'green')
        )


@client.event
async def on_raw_reaction_add(payload):
    await update_msg(payload)


@client.event
async def on_raw_reaction_remove(payload):
    await update_msg(payload)


def main():
    token = environ['TOKEN']
    is_ready = False

    client.run(token)


if __name__ == '__main__':
    main()
