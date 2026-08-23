"""One-time interactive login that creates radar's Telegram session.

Run this ONCE, by hand, on a machine you are sitting at. It asks for a phone
number and the code Telegram sends to it, and writes `radar_telegram.session`
in the working directory. The ingest daemon reuses that file and never prompts
again.

    cd personal_apps && PYTHONPATH=. python scripts/telegram_login.py

WHAT THE SESSION FILE IS
    Full account access. Not a token that can be scoped or a key that can be
    rotated from a dashboard -- anyone holding the file is signed in as you,
    with no password and no second factor. It is gitignored, it belongs at
    mode 600, and it is the reason this script exists as a deliberate manual
    step rather than something the daemon does on first run.

    To revoke it: Telegram app -> Settings -> Devices -> terminate the session.

WHY MTPROTO AND NOT A BOT
    A bot can only read channels it has been added to, and nobody is adding a
    bot to a public alert channel they run. Reading public channel history
    needs a user account, which is what this signs in.

    Reading message history is the low-risk side of Telegram automation.
    Member-list enumeration is the flagged spam vector; radar never does it.
"""
import asyncio
import os
import pathlib

from dotenv import load_dotenv
from telethon import TelegramClient

SESSION_NAME = 'radar_telegram'


async def main():
    load_dotenv(override=True)

    api_id = os.getenv('TELEGRAM_API_ID')
    api_hash = os.getenv('TELEGRAM_API_HASH')
    if not api_id or not api_hash:
        raise SystemExit(
            'TELEGRAM_API_ID and TELEGRAM_API_HASH must be in the root .env. '
            'Get them from my.telegram.org -> API development tools.')

    client = TelegramClient(SESSION_NAME, int(api_id), api_hash)
    # start() prompts for the phone number, then the login code, then the
    # cloud password if two-factor is enabled. All three are typed here and
    # go straight to Telegram; nothing is echoed or stored beyond the session.
    await client.start()

    me = await client.get_me()
    session_file = pathlib.Path(f'{SESSION_NAME}.session').resolve()
    print(f'\nSigned in as {me.username or me.first_name} (id {me.id}).')
    print(f'Session written to {session_file}')
    print('\nThis file is full account access. Keep it out of git, chmod 600,')
    print('and revoke it from Telegram -> Settings -> Devices if it leaks.')

    await client.disconnect()


if __name__ == '__main__':
    asyncio.run(main())
