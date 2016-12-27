__author__ = "Caleb Johnson <me@calebj.io>"
__copyright__ = "Copyright 2016 Caleb Johnson and Holocor, LLC"
__version__ = '2.0'

__doc__ = """
Selfbot wrapper by Caleb Johnson (GrumpiestVulcan/calebj#7377/me@calebj.io)

Red core originally by Twentysix26 and improved upon by many

For support or to report a bug, message me @calebj#7377 in either the
official Red server or Cog Support server (https://discord.gg/2DacSZ7)
"""

import asyncio
import sys
import functools
import discord
import traceback
from discord.ext import commands
from discord.ext.commands.bot import _get_variable
from io import TextIOWrapper
from red import Bot, initialize, main, set_cog
from getpass import getpass


DEFAULT_PREFIX = []
DELETE_PREFIX = 'd'  # Prepend prefix with this to delete trigger message
APPEND_PREFIX = 'a'  # prepend prefix with this to leave trigger message
EDIT_PREFIX = 's'    # default behavior, used in short

selfs = ['self,', 'self, ']
short_prefix = '!'
for pp in (DELETE_PREFIX, APPEND_PREFIX, EDIT_PREFIX):
    for p in selfs:
        if not p.startswith(pp):
            p = pp + p
        DEFAULT_PREFIX.append(p)
    DEFAULT_PREFIX.append(pp + short_prefix)
DEFAULT_PREFIX = sorted(DEFAULT_PREFIX, reverse=True)


description = ("Red Selfbot - A multifunction Discord bot by Twentysix, "
               "modified by GrumpiestVulcan (calebj#7377) to be run as a "
               "selfbot.")


def inject_context(ctx, coro):
    @functools.wraps(coro)
    @asyncio.coroutine
    def wrapped(*args, **kwargs):
        _internal_channel = ctx.message.channel
        _internal_author = ctx.message.author
        _internal_context = ctx  # necessary modification

        try:
            ret = yield from coro(*args, **kwargs)
        except Exception as e:
            raise commands.CommandInvokeError(e) from e
        return ret
    return wrapped


class SelfBot(Bot):
    def __init__(self, *args, pm_help=False, **kwargs):
        super().__init__(*args, self_bot=True, pm_help=False, **kwargs)

    def say(self, content=None, *args, **kwargs):
        ctx = _get_variable('_internal_context')
        destination = ctx.message.channel

        extensions = ('delete_after', 'delete_before')
        params = {k: kwargs.pop(k, None) for k in extensions}

        selfedit = (not ctx.prefix.startswith(APPEND_PREFIX) and
                    not ctx.message.edited_timestamp)
        selfdel = ctx.prefix.startswith(DELETE_PREFIX)

        if selfedit or selfdel:
            if selfdel:
                coro = asyncio.sleep(0)
                params['delete_before'] = ctx.message
            else:
                coro = self.edit_message(ctx.message, new_content=content,
                                         *args, **kwargs)
        else:
            coro = self.send_message(destination, content, *args, **kwargs)
        return self._augmented_msg(coro, **params)

    # We can't reply to anyone but ourselves
    reply = say

    def upload(self, *args, **kwargs):
        ctx = _get_variable('_internal_context')
        destination = ctx.message.channel

        extensions = ('delete_after', 'delete_before')
        params = {k: kwargs.pop(k, None) for k in extensions}

        coro = self.send_file(destination, *args, **kwargs)
        return self._augmented_msg(coro, **params)

    @asyncio.coroutine
    def _augmented_msg(self, coro, **kwargs):

        delete_before = kwargs.get('delete_before')
        if delete_before:
            yield from self.delete_message(delete_before)

        msg = yield from coro

        delete_after = kwargs.get('delete_after')
        if delete_after is not None:
            @asyncio.coroutine
            def delete():
                yield from asyncio.sleep(delete_after)
                yield from self.delete_message(msg)

            discord.compat.create_task(delete(), loop=self.loop)

        return msg

    def user_allowed(self, message):
        return message.author.id == self.user.id


def interactive_setup(settings):
    first_run = settings.bot_settings == settings.default_settings

    if first_run:
        print("Red selfbot - First run configuration\n"
              "If you use two-factor authentication, you must use a token "
              "below.\nTo obtain your token, press ctrl-shift-i in the "
              "discord client, click the 'console' tab, and enter "
              "'localStorage.token' in the console that appears.")

    if not settings.login_credentials:
        print("\nInsert your email or user session token:")
        while settings.token is None and settings.email is None:
            choice = input("> ")
            if "@" not in choice and len(choice) >= 50:  # Assuming token
                settings.token = choice
            elif "@" in choice:
                settings.email = choice
                settings.password = getpass()
            else:
                print("That doesn't look like a valid token.")
        settings.save_settings()

    if not settings.prefixes:
        settings.prefixes = DEFAULT_PREFIX
        settings.save_settings()

    if first_run:
        print("\nThe configuration is done. Leave this window always open to"
              " keep Red online.\nAll commands will have to be issued through"
              " Discord's chat, *this window will now be read only*.\n"
              "Please read this guide for a good overview on how Red works:\n"
              "https://twentysix26.github.io/Red-Docs/red_getting_started/\n"
              "Press enter to continue")
        input("\n")


if __name__ == '__main__':
    # Override inject_context function to pass full ctx
    commands.core.inject_context = inject_context

    sys.stdout = TextIOWrapper(sys.stdout.detach(),
                               encoding=sys.stdout.encoding,
                               errors="replace",
                               line_buffering=True)

    bot = initialize(bot_class=SelfBot)
    loop = asyncio.get_event_loop()
    error = False

    try:
        if not bot.settings.no_prompt:
            interactive_setup(bot.settings)
        print(__doc__)
        loop.run_until_complete(main(bot))

    except discord.LoginFailure:
        error = True
        bot.logger.error(traceback.format_exc())
        if not bot.settings.no_prompt:
            choice = input("Invalid login credentials. If they worked before "
                           "Discord might be having temporary technical "
                           "issues.\nIn this case, press enter and try again "
                           "later.\nOtherwise you can type 'reset' to reset "
                           "the current credentials and set them again the "
                           "next start.\n> ")
            if choice.lower().strip() == "reset":
                bot.settings.token = None
                bot.settings.email = None
                bot.settings.password = None
                bot.settings.save_settings()
    except KeyboardInterrupt:
        loop.run_until_complete(bot.logout())
    except:
        error = True
        bot.logger.error(traceback.format_exc())
        loop.run_until_complete(bot.logout())
    finally:
        loop.close()
        if error:
            exit(1)
