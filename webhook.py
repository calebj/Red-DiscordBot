import discord
from discord import utils
from discord.http import Route
from discord.mixins import Hashable
import aiohttp
import io
from os.path import split as path_split


class Webhook(Hashable):
    """Represents a Discord webhook.

    Depending on the way this object was created, some of the attributes can
    have a value of ``None``.

    Supported Operations:

    +-----------+---------------------------------------+
    | Operation |              Description              |
    +===========+=======================================+
    | x == y    | Checks if two webhooks are equal.     |
    +-----------+---------------------------------------+
    | x != y    | Checks if two webhooks are not equal. |
    +-----------+---------------------------------------+
    | hash(x)   | Return the webhook's ID.              |
    +-----------+---------------------------------------+
    | str(x)    | Returns the webhook's name.           |
    +-----------+---------------------------------------+

    Attributes
    -----------
    id : str
        The webhook's ID.
    token : bool
        The webhook's secure token.
    name : str
        The default name of the webhook.
    avatar : str
        The default avatar of the webhook.
    user : Optional[:class:`User`]
        The user who created the webhook. May be `None` in certain cases.
    channel : :class:`Channel`
        The channel the webhook belongs to.
    server : :class:`Server`
        The server the webhook belongs to.
    created_at : `datetime.datetime`
        A datetime object denoting the time the webhook was created.
    """

    __slots__ = ['id', 'token', 'avatar', 'name', 'user', 'channel']

    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.token = kwargs.get('token')
        self.avatar = kwargs.get('avatar')
        self.name = kwargs.get('name')

        user_data = kwargs.get('user')
        self.user = None if user_data is None else discord.User(**user_data)
        self.channel = kwargs.get('channel')

    def __str__(self):
        return self.name

    @property
    def created_at(self):
        "Returns the webhook's creation time in UTC."
        return utils.snowflake_time(self.id)

    @property
    def avatar_url(self):
        "Returns the URL version of the webhook's avatar. Returns an empty string if it has no avatar."
        if self.avatar is None:
            return ''
        return 'https://cdn.discordapp.com/avatars/{0.id}/{0.avatar}.png'.format(self)

    @property
    def server(self):
        "Returns the server the webhook belongs to."
        return None if self.channel is None else self.channel.server


class WebhookBotMixin:
    "Client mixin to enable webhook functionality"
    def _fill_webhook_data(self, data):
        server = self.connection._get_server(data['guild_id'])
        if server is not None:
            ch_id = data['channel_id']
            channel = server.get_channel(ch_id)
        else:
            server = discord.Object(id=data['guild_id'])
            channel = discord.Object(id=data['channel_id'])
        data['server'] = server
        data['channel'] = channel

    async def get_channel_webhooks(self, channel: discord.Channel):
        if type(channel) is not discord.Channel:
            raise TypeError('channel parameter must be of type Channel')

        r = Route('GET', '/channels/{channel.id}/webhooks', channel=channel)
        data = await self.http.request(r)

        hooks = []
        for hook in data:
            self._fill_webhook_data(hook)
            hooks.append(Webhook(**hook))

        return hooks

    async def get_server_webhooks(self, server: discord.Server):
        if type(server) is not discord.Server:
            raise TypeError('server parameter must be of type Server')

        r = Route('GET', '/guilds/{server.id}/webhooks', server=server)
        data = await self.http.request(r)

        hooks = []
        for hook in data:
            self._fill_webhook_data(hook)
            hooks.append(Webhook(**hook))

        return hooks

    async def get_webhook(self, id: str, token: str = None):
        resource = '/webhooks/{webhook_id}'
        if token is not None:
            resource += '/{token}'

        r = Route('GET', resource, webhook_id=id, token=token)

        data = await self.http.request(r)
        self._fill_webhook_data(data)
        return Webhook(**data)

    async def edit_webhook(self, webhook, name=None, avatar=None, use_token=False):
        if type(webhook) is not Webhook:
            raise TypeError('webhook parameter must be of type Webhook')

        data = {}

        if avatar is not None:
            data['avatar'] = utils._bytes_to_base64_data(avatar)

        if name is not None:
            data['name'] = str(name)

        resource = '/webhooks/{webhook.id}'
        if use_token:
            resource += '/{webhook.token}'

        r = Route('PATCH', resource, webhook=webhook)

        data = await self.http.request(r, json=data)
        self._fill_webhook_data(data)
        return Webhook(**data)

    async def create_webhook(self, channel, name: str, avatar=None):
        if type(channel) is not discord.Channel:
            raise TypeError('channel parameter must be of type Channel')

        data = {}

        if avatar is not None:
            data['avatar'] = utils._bytes_to_base64_data(avatar)

        if name is not None:
            data['name'] = str(name)

        r = Route('POST', '/channels/{channel_id}/webhooks', channel_id=channel.id)
        data = await self.http.request(r, json=data)
        self._fill_webhook_data(data)
        return Webhook(**data)

    async def delete_webhook(self, webhook: Webhook, use_token=False):
        if type(webhook) is not Webhook:
            raise TypeError('webhook parameter must be of type Webhook')

        resource = '/webhooks/{webhook.id}'
        if use_token:
            resource += '/{webhook.token}'

        r = Route('DELETE', resource, webhook=webhook)
        return await self.http.request(r)

    async def webhook_message(self, webhook, content, *, tts=False, embed=None):
        if type(webhook) is not Webhook:
            raise TypeError('webhook parameter must be of type Webhook')

        content = str(content) if content is not None else None

        if embed is not None:
            embed = embed.to_dict()

        data = await self._post_webhook_message(webhook, content, tts=tts, embed=embed)
        channel = webhook.channel
        message = self.connection._create_message(channel=channel, **data)
        return message

    async def webhook_file(self, webhook, fp, *, filename=None, content=None, tts=False):
        if type(webhook) is not Webhook:
            raise TypeError('webhook parameter must be of type Webhook')

        try:
            with open(fp, 'rb') as f:
                buffer = io.BytesIO(f.read())
                if filename is None:
                    _, filename = path_split(fp)
        except TypeError:
            buffer = fp

        content = str(content) if content is not None else None
        data = await self._post_webhook_file(webhook, buffer, filename=filename,
                                             content=content, tts=tts)
        channel = webhook.channel
        message = self.connection._create_message(channel=channel, **data)
        return message

    def _post_webhook_message(self, webhook, content, *, tts=False, embed=None):
        r = Route('POST', '/webhooks/{webhook.id}/{webhook.token}', webhook=webhook)
        payload = {}

        if content:
            payload['content'] = content

        if tts:
            payload['tts'] = True

        if embed:
            payload['embeds'] = [embed]

        return self.http.request(r, json=payload, params={'wait': True})

    def _post_webhook_file(self, webhook, buffer, *, filename=None, content=None, tts=False):
        r = Route('POST', '/webhooks/{webhook.id}/{webhook.token}', webhook=webhook)
        form = aiohttp.FormData()

        payload = {'tts': tts}
        if content:
            payload['content'] = content

        form.add_field('payload_json', utils.to_json(payload))
        form.add_field('file', buffer, filename=filename, content_type='application/octet-stream')

        return self.http.request(r, data=form, params={'wait': True})
