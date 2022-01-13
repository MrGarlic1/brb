# Bot functions

from termcolor import colored
from yaml import load, dump, Loader, Dumper
from requests import post


class Prefix:
    def __init__(self, guild_id, char):
        self.guild_id = guild_id
        self.char = char

    def __repr__(self):
        return f'<id={self.guild_id}> <char={self.char}>'


def has_role(user, role_id):
    if role_id in [y.id for y in user.roles]:
        return True
    else:
        return False


def chk_file(filename):
    try:
        f = open(filename, 'r')
    except FileNotFoundError:
        f = open(filename, 'w')
        print(colored(f'{filename} does not exist, new file created.', 'yellow'))
    f.close()


def remove_blanks(word_list):
    element = 0
    while element < len(word_list):
        if word_list[element] == '':
            del word_list[element]
            element -= 1
        element += 1
    return word_list


def is_command(text, prefix):
    if not text.content.lower().startswith(prefix):
        return False
    if text.author.bot:
        return False
    if str(text.channel.type) == 'private':
        return False
    if len(text.content) <= 1:
        return False
    if text.content[1] == ' ':
        return False
    return True


def process_args(raw_arguments):
    arguments = remove_blanks(raw_arguments)
    i = 0
    while i < len(arguments):
        if arguments[i].startswith('\"') and arguments[i] != '\"':  # Combines quoted arguments
            if arguments[i].endswith('\"'):
                arguments[i] = arguments[i][1:-1]
            else:
                arguments[i] = arguments[i][1:]
                j = i + 1
                try:
                    while not arguments[j].endswith('\"'):
                        arguments[i] += ' ' + arguments[j]
                        del arguments[j]
                    arguments[i] += ' ' + arguments[j][:-1]
                    del arguments[j]
                except IndexError:  # No closing quote
                    arguments = remove_blanks(raw_arguments)
        i += 1
    if '' in arguments:  # Error catching for weird quotes
        arguments = remove_blanks(raw_arguments)
    return arguments


def time_to_string(seconds):
    days = str(seconds // (24 * 3600))
    seconds %= (24 * 3600)
    hours = str(seconds // 3600)
    seconds %= 3600
    mins = str(seconds // 60)
    seconds = str(seconds % 60)

    # Grammatical correctness for plural vs singular numbers
    day_ind = ' day, ' if days == '1' else ' days, '
    hour_ind = ' hour, ' if hours == '1' else ' hours, '
    min_ind = ' minute' if mins == '1' else ' minutes'
    sec_ind = ' second' if seconds == '1' else ' seconds'

    if days == '0':
        if hours == '0':
            if mins == '0':
                return seconds + sec_ind
            return f'{mins}{min_ind}, and {seconds}{sec_ind}'
        return f'{hours}{hour_ind}{mins}{min_ind}, and {seconds}{sec_ind}'
    return f'{days}{day_ind}{hours}{hour_ind}{mins}{min_ind}, and {seconds}{sec_ind}'


def string_to_time(time_string):
    cooldown = 0
    try:
        for time_element in time_string:
            if time_element[-1].lower() == 'd':
                cooldown += int(time_element[:-1]) * 86400
            elif time_element[-1].lower() == 'h':
                cooldown += int(time_element[:-1]) * 3600
            elif time_element[-1].lower() == 'm':
                cooldown += int(time_element[:-1]) * 60
            elif time_element[-1].lower() == 's':
                cooldown += int(time_element[:-1])
            else:
                try:
                    cooldown += int(time_element)
                except TypeError:
                    pass
        return cooldown

    except ValueError:
        return False
