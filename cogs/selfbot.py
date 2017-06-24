import discord
from discord.ext import commands
from .utils.dataIO import dataIO
from .utils import checks
from .utils.chat_formatting import box
from datetime import datetime
from enum import IntFlag
import os
import asyncio

PATH = 'data/selfbot/'
JSON = PATH + 'settings.json'
COMMAND_MODES = ['EDIT', 'NORMAL', 'SILENT', 'FUSED']

DEFAULT_JSON = {
    'NOTIF_CHANNEL'  : None,
    'NOTIF_HOOK'     : None,

    'EDIT_FLAG'      : 's',   # edits command message to be first reply
    'NORMAL_FLAG'    : 'a',   # leaves command message, posts replies seperate
    'SILENT_FLAG'    : 'q',   # deletes command message and drops responses
    'FUSED_FLAG'     : 'f',   # deletes command and repl[y|ies] after a time
    'FUSE_TIMER'     : 60,    # time to wait before deleting
    'FUSED_EDIT'     : True,  # edit in-place or reply normally when fused?
    'LOCKOUT_PREFIX' : 'selfbot, please execute the following command: ',
    'FLAGLESS_MODE'  : None
}


class MessageAction(IntFlag):
    DEFAULT = 0x00
    NORMAL  = 0x01
    DELCMD  = 0x02
    EDIT    = 0x04
    FUSED   = 0x08
    NOREPLY = 0x10
    SILENT  = 0x02 | 0x10


class SelfBot:
    "Utility cog for selfbot functionality and management"
    def __init__(self, bot):
        self.bot = bot
        self.settings = dataIO.load_json(JSON)
        self.selfbot_server = None
        self.notif_hook = None
        self.notif_channel = None
        self.task_handle = self.bot.loop.create_task(self.loop_task())
        self.fuse_handles = {}
        self.public_whisper = set()

        self.update_prefix_cache()

    def __unload(self):
        # NOT cancelling fuse tasks
        self.task_handle.cancel()

    def save(self):
        dataIO.save_json(JSON, self.settings)

    def prefix_manager(self, bot, message):
        return self.prefix_cache

    def update_prefix_cache(self):
        base_prefixes = list(self.bot.settings.prefixes)
        prefixes = {self.settings.get('LOCKOUT_PREFIX')}

        if self.settings.get('FLAGLESS_MODE'):
            prefixes |= set(base_prefixes)

        for mode in COMMAND_MODES:
            mode_flag = self.settings.get(mode + '_FLAG')
            if not mode_flag:
                continue
            for p in base_prefixes:
                to_add = p if p.startswith(mode_flag) else (mode_flag + p)
                prefixes.add(to_add)

        self.prefix_cache = sorted(filter(None, prefixes), reverse=True)

    def ctx_action(self, ctx):
        prefix = ctx.prefix
        msg = ctx.message

        if prefix == self.settings.get('LOCKOUT_PREFIX'):
            return MessageAction.NORMAL

        action = MessageAction(0)

        for mode in COMMAND_MODES:
            mode_flag = self.settings.get(mode + '_FLAG')
            if mode_flag and prefix.startswith(mode_flag):
                action = MessageAction[mode]
                break

        if action & MessageAction.FUSED:
            if self.settings['FUSED_EDIT']:
                action |= MessageAction.EDIT
            else:
                action |= MessageAction.NORMAL

        # don't edit if message has already been edited
        if action & MessageAction.EDIT and msg.edited_timestamp:
            action ^= (MessageAction.NORMAL | MessageAction.EDIT)


        flagless_mode = self.settings.get('FLAGLESS_MODE')
        if flagless_mode in COMMAND_MODES and action == MessageAction.DEFAULT:
            return MessageAction[flagless_mode]

        return action

    def mode_flag_usedby(self, new_flag):
        for mode in COMMAND_MODES:
            mode_flag = self.settings.get(mode + '_FLAG')
            if not mode_flag:
                continue
            elif mode_flag == new_flag:
                return mode

    # Background tasks

    async def loop_task(self):
        try:
            await self.bot.wait_until_ready()

            wc_id = self.settings['NOTIF_CHANNEL']
            if wc_id:
                self.notif_channel = self.bot.get_channel(wc_id)

            if hasattr(self.bot, 'get_webhook'):
                wh_tuple = self.settings['NOTIF_HOOK']
                if type(wh_tuple) is list and len(wh_tuple) == 2:
                    id, token = self.settings['NOTIF_HOOK']
                    try:
                        hook = await self.bot.get_webhook(id, token)
                        self.notif_hook = hook
                    except discord.errors.NotFound:
                        self.settings['NOTIF_HOOK'] = None
                        self.save()

                if self.notif_channel and not self.notif_hook:
                    perms = self.notif_channel.permissions_for(self.bot.user)
                    if perms.manage_webhooks:
                        await self.create_sbnc_webhook(self.notif_channel)

            if self.notif_channel:
                self.selfbot_server = self.notif_channel.server

        except asyncio.CancelledError:
            pass

    async def fuse_task(self, message, delay):
        if not isinstance(delay, (int, float)) or delay < 0:
            raise TypeError('delay must be zero or positive')

        try:
            await asyncio.sleep(delay)

            try:
                await self.bot.delete_message(message)
            except:
                pass

            if message.id in self.fuse_handles:
                del self.fuse_handles[message.id]

        except asyncio.CancelledError:
            pass

    # Custom message posting functions with modifiers

    def schedule_fuses(self, *messages):
        delay = self.settings['FUSE_TIMER']
        for message in messages:
            if message.id in self.fuse_handles:
                continue
            handle = self.bot.loop.create_task(self.fuse_task(message, delay))
            self.fuse_handles[message.id] = handle

    async def confirm_whisper_post(self, err):
        msg = ('For your safety, a whisper message was suppressed. '
               'Normally, it would go to your designated selfbot whisper '
               'channel. However, %s. Reply "post it here" within 30s to '
               'do so.' % err)

        msg = await self.bot.say(msg)

        def check(msg):
            return msg.content.lower().strip('.!') == 'post it here'

        reply = await self.bot.wait_for_message(timeout=30, author=msg.author,
                                                channel=msg.channel,
                                                check=check)
        await self.bot.delete_message(msg)
        return reply

    async def upload(self, ctx, *args, **kwargs):
        action = self.ctx_action(ctx)
        to_fuse = []
        ret = ctx.message

        # Can't upload a file during edit, so delete to replace instead.
        if action & (MessageAction.EDIT | MessageAction.DELCMD):
            try:
                await self.bot.delete_message(ctx.message)
            except discord.Errors.NotFound:
                pass
        else:
            to_fuse.append(ctx.message)

        if not action & MessageAction.NOREPLY:
            ret = await self.bot.upload(*args, skip_selfbot=True, **kwargs)
            to_fuse.append(ret)

        if action & MessageAction.FUSED:
            self.schedule_fuses(*to_fuse)

        return ret

    async def say(self, ctx, content=None, **kwargs):
        action = self.ctx_action(ctx)
        to_fuse = []
        ret = ctx.message

        if action & MessageAction.DELCMD:
            try:
                await self.bot.delete_message(ctx.message)
            except discord.errors.NotFound:
                pass
        else:
            to_fuse.append(ctx.message)

        if action & MessageAction.EDIT and not action & MessageAction.DELCMD:
            try:
                coro = self.bot.edit_message(ctx.message, new_content=content,
                                             **kwargs)
                ret = await coro
                ctx.message.edited_timestamp = ret.edited_timestamp

            except discord.errors.NotFound:
                pass

        if ret == ctx.message and not action & MessageAction.NOREPLY:
            ret = await self.bot.say(content, skip_selfbot=True, **kwargs)
            to_fuse.append(ret)

        if action & MessageAction.FUSED:
            self.schedule_fuses(*to_fuse)

        return ret

    # Whisper functions. Webhook posting falls back to normal.

    async def whisper(self, ctx, *args, **kwargs):
        channel_id = self.get_notif_destination_id()
        channel = self.bot.get_channel(channel_id)

        if not channel_id:
            err = 'one has not been configured yet'
        elif not channel:
            err = 'the configured channel could not be found'
        else:
            if self.notif_channel:
                try:
                    return await self.self_whisper(ctx, *args, **kwargs)
                except:
                    err = 'something went wrong posting the message'

        if ctx.message.id in self.public_whisper:
            return await self.say(ctx, *args, **kwargs)

        reply = await self.confirm_whisper_post(err)
        if reply:
            try:
                await self.bot.delete_message(reply)
            except:
                pass
            self.public_whisper.add(ctx.message.id)
            return await self.say(ctx, *args, **kwargs)

        return ctx.message

    async def self_whisper(self, ctx, *args, **kwargs):
        action = self.ctx_action(ctx)
        to_fuse = []
        ret = ctx.message
        cwmsg = None

        if action & MessageAction.DELCMD:
            try:
                await self.bot.delete_message(ctx.message)
            except discord.errors.NotFound:
                pass
        else:
            to_fuse.append(ctx.message)

        if not action & MessageAction.NOREPLY:
            ret = await self.send_self_message(*args, **kwargs)
            to_fuse.append(ret)

        cw_text = 'Check %s for a whisper message.' % self.notif_channel.mention
        if action & MessageAction.EDIT and not action & MessageAction.DELCMD:
            try:
                coro = self.bot.edit_message(ctx.message, new_content=cw_text)
                cwmsg = await coro
                ctx.message.edited_timestamp = cwmsg.edited_timestamp
            except discord.errors.NotFound:
                pass

        if not cwmsg and not action & MessageAction.NOREPLY:
            cwmsg = await self.bot.say(cw_text, skip_selfbot=True)
            to_fuse.append(cwmsg)

        if action & MessageAction.FUSED:
            self.schedule_fuses(*to_fuse)

        return ret

    async def send_self_file(self, fp, **kwargs):
        if not self.notif_channel:
            raise RuntimeError('No selfbot whisper channel has been set.')

        elif not self.notif_hook:
            try:
                hook = await self.create_sbnc_webhook(self.notif_channel)
                msg = await self.bot.webhook_file(hook, fp, **kwargs)
            except:
                msg = await self.bot.send_file(self.notif_channel, fp, **kwargs)
        else:
            msg = await self.bot.webhook_file(self.notif_hook, fp, **kwargs)
        return msg

    async def send_self_message(self, content=None, **kwargs):
        if not self.notif_channel:
            raise RuntimeError('No selfbot whisper channel has been set.')
        elif not self.notif_hook:
            try:
                hook = await self.create_sbnc_webhook(self.notif_channel)
                msg = await self.bot.webhook_message(hook, content, **kwargs)
            except:
                msg = await self.bot.send_message(self.notif_channel, content, **kwargs)
        else:
            msg = await self.bot.webhook_message(self.notif_hook, content, **kwargs)
        return msg

    def get_notif_destination_id(self):
        if self.notif_channel:
            return self.notif_channel.id
        return None

    def get_notif_destination(self):
        return self.notif_channel

    async def create_sbnc_webhook(self, channel):
        if not hasattr(self.bot, 'create_webhook'):
            raise RuntimeError('Bot is missing webhook features.')

        avatar = self.bot.user.avatar
        if avatar:
            avatar_url = 'https://cdn.discordapp.com/avatars/{0.id}/{0.avatar}.png'
            avatar_url = avatar_url.format(self.bot.user)
        else:
            avatar_url = self.bot.user.default_avatar_url

        async with self.bot.http.session.get(avatar_url) as r:
            avatar = await r.read()

        hook = await self.bot.create_webhook(channel, 'SelfBot notifications',
                                             avatar=avatar)

        self.notif_hook = hook
        self.settings['NOTIF_HOOK'] = [hook.id, hook.token]
        self.save()
        return hook

    # Commands

    @commands.group(pass_context=True)
    @checks.is_owner()
    async def sbset(self, ctx):
        if ctx.invoked_subcommand is None:
            await self.bot.send_cmd_help(ctx)

            channel, hook = ['not set'] * 2
            if self.notif_channel:
                channel = '#{0} in {0.server}'.format(self.notif_channel)
            if self.notif_hook:
                hook = '{0.name} (ID {0.id})'.format(self.notif_hook)

            modelines = []
            for mode in COMMAND_MODES:
                line = '{} mode flag'.format(mode.title()).ljust(17) + ' : '
                line += self.settings[mode.upper() + '_FLAG'] or '[none]'
                modelines.append(line)

            msg = '\n'.join(modelines + [
                'Fuse timer length : %is' % self.settings['FUSE_TIMER'],
                'Fused edit mode   : %s'  % self.settings['FUSED_EDIT'],
                'Emergency prefix  : ' + (self.settings.get('LOCKOUT_PREFIX') or '[none]'),
                'Whisper channel   : ' + channel,
                'Whisper webhook   : ' + hook,
                'Flagless mode     : ' + (self.settings.get('FLAGLESS_MODE') or '[none]'),
            ])
            await self.bot.say('Current settings:\n' + box(msg))

    async def set_flag_common(self, mode, flag):
        taken = self.mode_flag_usedby(flag)
        if self.settings[mode.upper() + '_FLAG'] == flag:
            flag_desc = ("'%s'" % flag) if flag else 'clear'
            await self.bot.say("The %s mode flag is already %s."
                               % (mode.lower(), flag_desc))
            return
        elif flag and taken:
            await self.bot.say('That flag is already being used for %s mode.'
                               % taken.lower())
            return
        else:
            self.settings[mode.upper() + '_FLAG'] = flag
            self.update_prefix_cache()
            self.save()
            set_desc = ("set to '%s'" % flag) if flag else 'cleared'
            await self.bot.say("%s mode flag has been %s."
                               % (mode.title(), set_desc))

    @sbset.command(name='normalflag')
    async def sbs_normal_prefix(self, *, flag: str = None):
        "Set the prefix flag for normal (seperate reply) mode."
        await self.set_flag_common('normal', flag)

    @sbset.command(name='editflag')
    async def sbs_edit_flag(self, *, flag: str = None):
        "Set the prefix flag for edit reply mode."
        await self.set_flag_common('edit', flag)

    @sbset.command(name='silentflag')
    async def sbs_silent_flag(self, *, flag: str = None):
        "Set the prefix flag for silent (delete command, no reply) mode."
        await self.set_flag_common('silent', flag)

    @sbset.command(name='fusedflag')
    async def sbs_fused_flag(self, *, flag: str = None):
        "Set the prefix flag for fused (self-delete) mode."
        await self.set_flag_common('fused', flag)

    @sbset.command(name='fusededit')
    async def sbs_fused_edit(self, on_off: bool):
        "Configures whether fused mode also uses edit."
        adj = 'enabled' if on_off else 'disabled'
        if on_off == self.settings['FUSED_EDIT']:
            await self.bot.say('Fuse edit mode was already %s.' % adj)
            return
        self.settings['FUSED_EDIT'] = on_off
        self.save()
        await self.bot.say('Fuse edit mode is now %s.' % adj)

    @sbset.command(name='fusetimer')
    async def sbs_fused_timer(self, seconds: int):
        "Configures how long to wait before deleting fused commands."
        if not seconds >= 1:
            await self.bot.say('Delay must be at least one second.')
            return
        elif seconds == self.settings['FUSE_TIMER']:
            await self.bot.say('Fuse delay is already %i seconds.' % seconds)
            return
        self.settings['FUSE_TIMER'] = seconds
        self.save()
        await self.bot.say('Fuse delay set to %i seconds.' % seconds)

    @sbset.command(name='lockoutprefix')
    async def sbs_lockout_prefix(self, *, prefix: str = None):
        "Set an emergency prefix that will always work."
        setmsg = ("set to '%s'" % prefix) if prefix else 'disabled'

        if prefix == self.settings.get('LOCKOUT_PREFIX'):
            await self.bot.say('Emergency prefix was already %s.' % setmsg)
            return

        await self.bot.say('Emergency prefix %s.' % setmsg)
        self.settings['LOCKOUT_PREFIX'] = prefix
        self.update_prefix_cache()
        self.save()

    @sbset.command(name='flagless')
    async def sbs_fused_edit(self, mode: str = None):
        "Configures which mode to use for commands run with a flagless prefix."
        setmsg = ("set to %s" % mode.lower()) if mode else 'disabled'
        current = self.settings.get('FLAGLESS_MODE')
        if (mode and mode.lower()) == (current and current.lower()):
            await self.bot.say('Flagless mode was already %s.' % setmsg)
            return
        elif mode and (mode.upper() not in COMMAND_MODES):
            await self.bot.say("'%s' isn't a valid mode. Available modes: %s."
                               % (mode, ', '.join(COMMAND_MODES).lower()))
            return

        self.settings['FLAGLESS_MODE'] = mode and mode.upper()
        self.update_prefix_cache()
        self.save()

        await self.bot.say('Flagless mode is now %s.' % setmsg)

    @sbset.group(pass_context=True, no_pm=True, invoke_without_command=True, name='channel')
    async def sbs_notif_channel(self, ctx, channel : discord.Channel = None):
        "Sets the selfbot notification channel"
        if ctx.invoked_subcommand is None or \
                isinstance(ctx.invoked_subcommand, commands.Group):
            channel = channel or ctx.message.channel
            existing_channel = self.settings['NOTIF_CHANNEL']

            if self.selfbot_server and channel.server != self.selfbot_server:
                await self.bot.say('You must choose a channel in your selfbot server.')
                return
            elif existing_channel:
                if existing_channel == channel.id:
                    await self.bot.say('Already set to use %s.' % channel.mention)
                else:
                    await self.bot.say('You must clear this setting with `%s clear` first.' %
                                       (ctx.prefix + ctx.command.qualified_name))
                return

            self.settings['NOTIF_CHANNEL'] = channel.id
            self.save()

            msg = await self.bot.say('Creating webhook... ')
            try:
                await self.create_sbnc_webhook(channel)
                await self.bot.edit_message(msg, msg.content + 'OK.')
            except Exception as e:
                await self.bot.edit_message(msg, msg.content + 'ERROR: %s' % e)

            await self.bot.say('Selfbot notification channel set to %s.'
                               % channel.mention)

    @sbs_notif_channel.command(no_pm=False, name='clear')
    async def sbs_clear_channel(self):
        "Clears the selfbot notification channel"
        if self.settings['NOTIF_CHANNEL'] is None:
            await self.bot.say('Nothing to clear.')
            return

        self.settings['NOTIF_CHANNEL'] = None

        if self.notif_hook:
            try:
                await self.bot.delete_webhook(self.notif_hook)
            except discord.errors.NotFound:
                pass
            finally:
                self.settings['NOTIF_HOOK'] = None

        self.save()

        await self.bot.say('Selfbot notification channel cleared.')

    # Event listeners

    async def on_message_delete(self, message):
        if message.id in self.fuse_handles:
            self.fuse_handles[message.id].cancel()
            del self.fuse_handles[message.id]

    async def on_message_edit(self, before, after):
        if self.bot.user_allowed(after):
            after.edited_timestamp = None
            await self.bot.process_commands(after)

    async def on_command_completion(self, command, ctx):
        if command.qualified_name == 'set prefix':
            self.update_prefix_cache()
        if ctx.message.id in self.public_whisper:
            self.public_whisper.remove(ctx.message.id)


def check_data():
    if not os.path.exists(PATH):
        print("Creating %s folder..." % PATH)
        os.makedirs(PATH)

    if not dataIO.is_valid_json(JSON):
        print("Creating empty %s" % JSON)
        dataIO.save_json(JSON, DEFAULT_JSON)


def setup(bot):
    if not getattr(bot, 'IS_SELFBOT', None) or \
            float(getattr(bot, '__version__', 0)) < 2.2:
        raise RuntimeError('This cog only works in calebj selfbot v2.2+')

    check_data()
    bot.add_cog(SelfBot(bot))
