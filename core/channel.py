"""Channel representation"""
from __future__ import annotations

import re
import json
import asyncio
import logging
from base64 import b64encode
from functools import cached_property
from typing import Any, SupportsInt, cast, TYPE_CHECKING

import aiohttp
from yarl import URL

from core.utils import Game, json_minify
from core.exceptions import MinerException, RequestException
from core.constants import CALL, GQL_OPERATIONS, ONLINE_DELAY, URLType

if TYPE_CHECKING:
    from core.twitch_client import TwitchClient
    from core.constants import JsonType, GQLOperation
    # Android-specific: ChannelList is a Kivy widget defined in ui/
    ChannelList = Any


logger = logging.getLogger("TwitchDrops")


class Stream:
    def __init__(
        self,
        channel: Channel,
        *,
        id: SupportsInt,
        game: JsonType | None,
        viewers: int,
        title: str,
    ):
        self.channel: Channel = channel
        self.broadcast_id = int(id)
        self.viewers: int = viewers
        self.drops_enabled: bool = not channel._twitch.settings.available_drops_check
        self.game: Game | None = Game(game) if game else None
        self.title: str = title
        self._stream_url: URLType | None = None

    @cached_property
    def _spade_payload(self) -> JsonType:
        # Android-specific: user_id accessed via self.channel._twitch._auth_state.user_id
        # This will be wired in S10 once TwitchClient auth state is confirmed
        payload = [
            {
                "event": "minute-watched",
                "properties": {
                    "broadcast_id": str(self.broadcast_id),
                    "channel_id": str(self.channel.id),
                    "channel": self.channel._login,
                    "hidden": False,
                    "live": True,
                    "location": "channel",
                    "logged_in": True,
                    "muted": False,
                    "player": "site",
                    "user_id": self.channel._twitch._auth_state.user_id,
                }
            }
        ]
        return {"data": (b64encode(json_minify(payload).encode("utf8"))).decode("utf8")}

    @classmethod
    def from_get_stream(cls, channel: Channel, channel_data: JsonType) -> Stream:
        stream = channel_data["stream"]
        settings = channel_data["broadcastSettings"]
        return cls(
            channel,
            id=stream["id"],
            game=settings["game"],
            viewers=stream["viewersCount"],
            title=settings["title"],
        )

    @classmethod
    def from_directory(
        cls, channel: Channel, channel_data: JsonType, *, drops_enabled: bool = False
    ) -> Stream:
        self = cls(
            channel,
            id=channel_data["id"],
            game=channel_data["game"],
            viewers=channel_data["viewersCount"],
            title=channel_data["title"],
        )
        self.drops_enabled = drops_enabled
        return self

    def __eq__(self, other: object) -> bool:
        if isinstance(other, self.__class__):
            return self.broadcast_id == other.broadcast_id
        return NotImplemented

    async def get_stream_url(self) -> URLType | None:
        # Android-specific: stream URL fetched but HLS not played; used only for _send_watch()
        if self._stream_url is not None:
            return self._stream_url
        playback_token_response: JsonType = await self.channel._twitch.gql_request(
            GQL_OPERATIONS["PlaybackAccessToken"].with_variables({"login": self.channel._login})
        )
        token_data: JsonType = playback_token_response["data"]["streamPlaybackAccessToken"]
        token_value = token_data["value"]
        token_signature = token_data["signature"]
        available_qualities: str = ''
        try:
            async with self.channel._twitch.request(
                "GET",
                URL(
                    "https://usher.ttvnw.net/api/channel/hls/"
                    f"{self.channel._login}.m3u8?sig={token_signature}&token={token_value}"
                ),
            ) as qualities_response:
                available_qualities = await qualities_response.text()
            try:
                available_json: JsonType = json.loads(available_qualities)
            except json.JSONDecodeError:
                pass
            else:
                if isinstance(available_json, list):
                    available_json = available_json[0]
                if "error" in available_json:
                    logger.error(f"Stream URL get error: \"{available_json['error']}\"")
                    self.channel.set_offline()
                return None
            self._stream_url = cast(URLType, URL(available_qualities.strip().split("\n")[-1]))
        except (aiohttp.InvalidURL, ValueError):
            self.channel._twitch.print(available_qualities)
            raise
        return self._stream_url


class Channel:
    __slots__ = (
        "_twitch", "_gui_channels", "id", "_login", "_display_name", "_spade_url",
        "_stream", "_pending_stream_up", "acl_based"
    )

    def __init__(
        self,
        twitch: TwitchClient,
        *,
        id: SupportsInt,
        login: str,
        display_name: str | None = None,
        acl_based: bool = False,
    ):
        self._twitch: TwitchClient = twitch
        self._gui_channels: Any = None  # Android-specific: set by UI layer when ready
        self.id: int = int(id)
        self._login: str = login
        self._display_name: str | None = display_name
        self._spade_url: URLType | None = None
        self._stream: Stream | None = None
        self._pending_stream_up: asyncio.Task[Any] | None = None
        self.acl_based: bool = acl_based

    @classmethod
    def from_acl(cls, twitch: TwitchClient, data: JsonType) -> Channel:
        return cls(
            twitch,
            id=data["id"],
            login=data["name"],
            display_name=data.get("displayName"),
            acl_based=True,
        )

    @classmethod
    def from_directory(
        cls, twitch: TwitchClient, data: JsonType, *, drops_enabled: bool = False
    ) -> Channel:
        channel = data["broadcaster"]
        self = cls(
            twitch, id=channel["id"], login=channel["login"], display_name=channel["displayName"]
        )
        self._stream = Stream.from_directory(self, data, drops_enabled=drops_enabled)
        return self

    def __repr__(self) -> str:
        if self._display_name is not None:
            name = f"{self._display_name}({self._login})"
        else:
            name = self._login
        return f"Channel({name}, {self.id})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, self.__class__):
            return self.id == other.id
        return NotImplemented

    def __hash__(self) -> int:
        return self.id

    @property
    def stream_gql(self) -> GQLOperation:
        return GQL_OPERATIONS["GetStreamInfo"].with_variables({"channel": self._login})

    @property
    def name(self) -> str:
        if self._display_name is not None:
            return self._display_name
        return self._login

    @property
    def url(self) -> URLType:
        # Android-specific: CLIENT_URL must be set on TwitchClient
        return URLType(f"{self._twitch._client_type.CLIENT_URL}/{self._login}")

    @property
    def iid(self) -> str:
        return str(self.id)

    @property
    def online(self) -> bool:
        return self._stream is not None

    @property
    def offline(self) -> bool:
        return self._stream is None and self._pending_stream_up is None

    @property
    def pending_online(self) -> bool:
        return self._stream is None and self._pending_stream_up is not None

    @property
    def game(self) -> Game | None:
        if self._stream is not None:
            return self._stream.game
        return None

    @property
    def viewers(self) -> int | None:
        if self._stream is not None:
            return self._stream.viewers
        return None

    @viewers.setter
    def viewers(self, value: int) -> None:
        if self._stream is not None:
            self._stream.viewers = value

    @property
    def drops_enabled(self) -> bool:
        if self._stream is not None:
            return self._stream.drops_enabled
        return False

    def display(self, *, add: bool = False) -> None:
        # Android-specific: GUI display replaced — implement in ui/
        pass

    def remove(self) -> None:
        # Android-specific: GUI removal replaced — implement in ui/
        if self._pending_stream_up is not None:
            self._pending_stream_up.cancel()
            self._pending_stream_up = None

    async def get_spade_url(self) -> URLType:
        SETTINGS_PATTERN: str = (
            r'src="(https://[\w.]+/config/settings\.[0-9a-f]{32}\.js)"'
        )
        SPADE_PATTERN: str = (
            r'"(?:spade_?url|beacon_?url)": ?"(https://[^"]+)"'
        )
        async with self._twitch.request("GET", self.url) as response1:
            streamer_html: str = await response1.text(encoding="utf8")
        match = re.search(SPADE_PATTERN, streamer_html, re.I)
        if not match:
            match = re.search(SETTINGS_PATTERN, streamer_html, re.I)
            if not match:
                raise MinerException("Error while spade_url extraction: step #1")
            streamer_settings = match.group(1)
            async with self._twitch.request("GET", streamer_settings) as response2:
                settings_js: str = await response2.text(encoding="utf8")
            match = re.search(SPADE_PATTERN, settings_js, re.I)
            if not match:
                raise MinerException("Error while spade_url extraction: step #2")
        return URLType(match.group(1))

    def _check_drops_enabled(self, available_drops: list[JsonType]) -> bool:
        return any(
            (
                (campaign := self._twitch._campaigns.get(campaign_data["id"])) is not None
                and campaign.can_earn(self, ignore_channel_status=True)
            )
            for campaign_data in available_drops
        )

    def external_update(self, channel_data: JsonType, available_drops: list[JsonType]) -> None:
        if not channel_data["stream"]:
            self._stream = None
            return
        stream = Stream.from_get_stream(self, channel_data)
        if not stream.drops_enabled:
            stream.drops_enabled = self._check_drops_enabled(available_drops)
        self._stream = stream

    async def get_stream(self) -> Stream | None:
        try:
            response: JsonType = await self._twitch.gql_request(self.stream_gql)
        except MinerException as exc:
            raise MinerException(f"Channel: {self._login}") from exc
        channel_data: JsonType | None = response["data"]["user"]
        if not channel_data:
            return None
        if self._display_name is None:
            self._display_name = channel_data["displayName"]
        if not channel_data["stream"]:
            return None
        stream = Stream.from_get_stream(self, channel_data)
        if not stream.drops_enabled:
            try:
                available_drops_campaigns: JsonType = await self._twitch.gql_request(
                    GQL_OPERATIONS["AvailableDrops"].with_variables({"channelID": str(self.id)})
                )
            except MinerException:
                logger.log(CALL, f"AvailableDrops GQL call failed for channel: {self._login}")
            else:
                stream.drops_enabled = self._check_drops_enabled(
                    available_drops_campaigns["data"]["channel"]["viewerDropCampaigns"] or []
                )
        return stream

    async def update_stream(self) -> bool:
        old_stream = self._stream
        self._stream = await self.get_stream()
        self._twitch.on_channel_update(self, old_stream, self._stream)
        return self._stream is not None

    async def _online_delay(self) -> None:
        await asyncio.sleep(ONLINE_DELAY.total_seconds())
        self._pending_stream_up = None
        await self.update_stream()

    def check_online(self) -> None:
        if self._pending_stream_up is None:
            self._pending_stream_up = asyncio.create_task(self._online_delay())
            self.display()

    def set_offline(self) -> None:
        needs_display: bool = False
        if self._pending_stream_up is not None:
            self._pending_stream_up.cancel()
            self._pending_stream_up = None
            needs_display = True
        if self.online:
            old_stream = self._stream
            self._stream = None
            self._twitch.on_channel_update(self, old_stream, self._stream)
            needs_display = False
        if needs_display:
            self.display()

    async def _send_watch(self) -> bool:
        if self._stream is None:
            return False
        stream_url = await self._stream.get_stream_url()
        if stream_url is None:
            return False
        async with self._twitch.request(
            "GET", stream_url, headers={"Connection": "close"}
        ) as chunks_response:
            if chunks_response.status >= 400:
                return False
            available_chunks: str = await chunks_response.text()
        available_chunks = re.sub(r'"url": ?".+}",', '', available_chunks)
        try:
            available_json: JsonType = json.loads(available_chunks)
        except json.JSONDecodeError:
            pass
        else:
            if isinstance(available_json, list):
                available_json = available_json[0]
            if "error" in available_json:
                logger.error(f"Send watch error: \"{available_json['error']}\"")
            return False
        chunks_list: list[str] = available_chunks.strip().split("\n")
        selected_chunk: str = chunks_list[-1]
        if selected_chunk == "#EXT-X-ENDLIST":
            selected_chunk = chunks_list[-2]
        stream_chunk_url: URLType = URLType(selected_chunk)
        async with self._twitch.request("HEAD", stream_chunk_url) as head_response:
            return head_response.status == 200

    async def send_watch(self) -> bool:
        if self._stream is None:
            return False
        if self._spade_url is None:
            self._spade_url = await self.get_spade_url()
        try:
            async with self._twitch.request(
                "POST", self._spade_url, data=self._stream._spade_payload
            ) as response:
                return response.status == 204
        except RequestException:
            return False
