__author__ = "Caleb Johnson <me@calebj.io>"
__copyright__ = "Copyright 2017 Caleb Johnson and Holocor, LLC"
__version__ = '2.2'

__doc__ = """
  ~= Selfbot wrapper v%s by Caleb Johnson (GrumpiestVulcan/me@calebj.io) =~

Red-DiscordBot core originally by Twentysix26 and improved upon by many.

For support or to report a bug, message me @calebj#7377 in either:
 - the Cog Support server (https://discord.gg/2DacSZ7), in #support_calebj, or
 - the official Red server (https://discord.gg/red)

Some third-party modules may violate Discord's terms of service if they cause
your selfbot to respond to other users. The authors are not responsible for
any consequences such behavior may have, and do not support such use cases.
""" % __version__

import asyncio
import sys
import functools
import traceback
from io import TextIOWrapper
from collections import OrderedDict
from getpass import getpass
from red import Bot, initialize, main, set_cog
import discord
from discord.ext import commands
from discord.ext.commands.bot import _get_variable
from webhook import WebhookBotMixin


DEFAULT_PREFIX = ['self, ', 'self,', '!']


description = ("Red Selfbot - A multifunction Discord bot by Twentysix, "
               "modified by GrumpiestVulcan (calebj#7377) to be run as a "
               "selfbot.")


class ODQueue():
    def __init__(self, items=(), maxlen=None):
        self._maxlen = maxlen
        self._od = OrderedDict((k, None) for k in items)

    def append(self, item):
        if item in self:
            self._od.move_to_end(item)
            return
        if len(self._od) == self._maxlen:
            self.popleft()
        self._od[item] = None

    def extend(self, items):
        for item in items:
            self.append(item)

    def pop(self):
        return self._od.popitem()[0]

    def popleft(self):
        return self._od.popitem(last=False)[0]

    def __contains__(self, item):
        return item in self._od

    def __len__(self):
        return len(self._od)


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


def get_selfbot_cog(bot):
    selfbot = bot.get_cog('SelfBot')
    if not selfbot:
        try:
            bot.load_extension('cogs.selfbot')
        except:
            return None
    return bot.get_cog('SelfBot')


def prefix_manager(bot, message):
    selfbot = get_selfbot_cog(bot)
    if not selfbot:
        return bot.settings.get_prefixes(message.server)
    else:
        return selfbot.prefix_manager(bot, message)


class SelfBot(Bot, WebhookBotMixin):
    IS_SELFBOT = True  # checked in selfbot-only cog loads
    __version__ = __version__
    __doc__ = __doc__

    def __init__(self, *args, pm_help=False, **kwargs):
        super().__init__(*args, self_bot=True, pm_help=False, **kwargs)
        self.bot_messages = ODQueue(maxlen=128)
        self.command_prefix = prefix_manager

    async def say(self, *args, skip_selfbot=False, **kwargs):
        ctx = _get_variable('_internal_context')

        selfbot = get_selfbot_cog(self)
        if selfbot and not skip_selfbot:
            msg = await selfbot.say(ctx, *args, **kwargs)
        else:
            msg = await super().say(*args, **kwargs)

        self.bot_messages.append(msg.id)
        return msg

    async def upload(self, *args, skip_selfbot=False, **kwargs):
        ctx = _get_variable('_internal_context')

        selfbot = get_selfbot_cog(self)
        if selfbot and not skip_selfbot:
            msg = await selfbot.upload(ctx, *args, **kwargs)
        else:
            msg = await super().upload(*args, **kwargs)

        self.bot_messages.append(msg.id)
        return msg

    async def send_message(self, destination, content=None, **kwargs):
        if content is not None:
            self.bot_messages.append((destination.id, content.strip()))

        selfbot = get_selfbot_cog(self)
        if selfbot and destination.id == self.user.id:
            msg = await selfbot.send_self_message(content, **kwargs)
        else:
            msg = await super().send_message(destination, content, **kwargs)

        self.bot_messages.append(msg.id)
        return msg

    async def send_file(self, destination, fp, **kwargs):
        content = kwargs.get('content')
        if content is not None:
            self.bot_messages.append((destination.id, content.strip()))

        selfbot = get_selfbot_cog(self)
        if selfbot and destination.id == self.user.id:
            msg = await selfbot.send_self_file(fp, **kwargs)
        else:
            msg = await super().send_file(destination, fp, **kwargs)

        self.bot_messages.append(msg.id)
        return msg

    def edit_message(self, message, new_content=None, **kwargs):
        self.bot_messages.append(message.id)
        return super().edit_message(message, new_content, **kwargs)

    def wait_for_message(self, timeout=None, *, author=None, channel=None, content=None, check=None):
        if author is not None and author.id == self.user.id:
            def new_check(message):
                result = self.user_allowed(message)
                if callable(check):
                    result = result and check(message)
                return result
        else:
            new_check = check

        return super().wait_for_message(timeout, author=author, channel=channel,
                                        content=content, check=new_check)

    # We can't reply to anyone but ourselves
    reply = say

    async def whisper(self, *args, skip_selfbot=False, **kwargs):
        ctx = _get_variable('_internal_context')

        selfbot = get_selfbot_cog(self)
        if selfbot and not skip_selfbot:
            msg = await selfbot.whisper(ctx, *args, **kwargs)
            self.bot_messages.append(msg.id)
            return msg

        msg = ('For your safety, a whisper message was suppressed. '
               'Normally, it would go to your designated selfbot whisper '
               'channel. However, the selfbot cog could not be loaded or '
               'used. Reply "post it anyway" within 30s to do so.')

        msg = await self.say(msg)

        def check(msg):
            return msg.content.lower().strip('.!') == 'post it anyway'

        reply = await self.wait_for_message(timeout=30, author=msg.author,
                                            channel=msg.channel,
                                            check=check)
        if reply:
            for m in (msg, reply):
                try:
                    await self.bot.delete_message(m)
                except:
                    pass
            msg = await self.say(*args, **kwargs)

        self.bot_messages.append(msg.id)
        return msg

    # default afk=True
    def change_presence(self, game=None, status=None, afk=True):
        return super().change_presence(game=game, status=status, afk=afk)

    def user_allowed(self, message):
        author_ok = message.author.id == self.user.id
        check_tup = (message.channel.id, message.content)
        botsent_ok = check_tup not in self.bot_messages
        botedit_ok = message.id not in self.bot_messages

        return author_ok and botsent_ok and botedit_ok


def interactive_setup(settings):
    first_run = settings.bot_settings == settings.default_settings

    if first_run:
        print("Red selfbot - First run configuration\n"
              "If you use two-factor authentication, you must use a token "
              "below. To obtain your token:\n"
              " 1. Press ctrl-shift-i in the discord client\n"
              " 2. Click the 'Application' tab and expand Local Storage\n"
              " 3. Click the discordapp.com item under Local Storage\n"
              " 4. Look for the 'token' key, and copy its value without quotes"
              )

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
        # NOTE: may become necessary to disable this in red.py if run here.
        if not bot.settings.no_prompt:
            interactive_setup(bot.settings)
        print(__doc__)
        get_selfbot_cog(bot)
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
