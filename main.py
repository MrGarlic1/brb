"""
Ben Samans
main.py
"""
from brbot.Core.bot import BrBot

import logging

from brbot.Core.botdata import token

logger = logging.getLogger(__name__)
logging.basicConfig(
    format='%(asctime)s %(levelname)s:%(name)s: %(message)8s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)


def main():
    try:
        bot = BrBot()
        bot.run(token)
    except Exception as e:
        logger.critical(f'Failed to start bot: {str(e)}')
        exit(1)


if __name__ == "__main__":
    main()
