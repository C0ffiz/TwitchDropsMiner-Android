"""Main Twitch client for drops mining"""
import asyncio
import logging
import json
from time import time
from copy import deepcopy
from collections import deque, OrderedDict
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
from typing import Optional, Any, NoReturn, TYPE_CHECKING

import aiohttp

from core.constants import (
    CALL, MAX_INT, CLIENT_ID, USER_AGENT, GQL_URL, GQL_OPERATIONS,
    State, PriorityMode, WATCH_INTERVAL, WebsocketTopic, MAX_CHANNELS,
)
from core.exceptions import (
    MinerException, LoginException, GQLException,
    CaptchaRequired, ExitRequest
)
from core.utils import (
    create_nonce, timestamp, Game, AwaitableValue,
    ExponentialBackoff, RateLimiter, chunk, task_wrapper,
)
from core.settings import Settings

if TYPE_CHECKING:
    from core.constants import JsonType

from core.websocket_client import WebsocketPool
from core.inventory import DropsCampaign, TimedDrop
from core.channel import Channel

logger = logging.getLogger("TwitchDrops")


class _NotificationsShim:
    """
    Android-specific: bridges inventory's notify_drop() call to TwitchClient.notify().
    Inventory calls self._twitch.notifications.notify_drop(drop) after claiming.
    """
    def __init__(self, twitch: "TwitchClient") -> None:
        self._twitch = twitch

    def notify_drop(self, drop) -> None:
        self._twitch.notify(
            "Drop Claimed",
            f"{drop.rewards_text()}\n{drop.campaign.game.name}"
        )


class TwitchClient:
    """Main Twitch client for mining drops."""

    def __init__(self, settings: Settings, callbacks: dict):
        self.settings = settings
        self.callbacks = callbacks

        # State
        self.state = State.IDLE
        self._running = False
        self._session: Optional[aiohttp.ClientSession] = None
        self._logged_in: AwaitableValue = AwaitableValue()
        self._state_change = asyncio.Event()  # Android-specific

        # Watch control
        self._watching_restart = asyncio.Event()  # Android-specific

        # Data
        self.inventory: list[DropsCampaign] = []
        self.channels: dict[int, Channel] = {}  # keyed by channel id
        self.watching_channel: AwaitableValue = AwaitableValue()  # Android-specific: was Optional[Channel]
        self.current_drop: Optional[TimedDrop] = None
        self.games: set[Game] = set()
        self.notifications = _NotificationsShim(self)  # Android-specific

        # Drop tracking (Android-specific: flat dicts for fast lookup)
        self._drops: dict[str, TimedDrop] = {}
        self._campaigns: dict[str, DropsCampaign] = {}

        # Game priority list
        self.wanted_games: list[Game] = []

        # Android-specific: renamed from websocket_pool to websocket
        self.websocket: Optional[WebsocketPool] = None

        # Tasks
        self._watch_task: Optional[asyncio.Task] = None
        self._mnt_task: Optional[asyncio.Task] = None  # Android-specific: was _maintenance_task
        self._mnt_triggers: deque = deque()  # Android-specific

        # GQL rate limiter (5 requests per second)
        self._gql_limiter = RateLimiter(capacity=5, window=1)  # Android-specific

    # ========================================================================
    # CALLBACKS
    # ========================================================================

    def _callback(self, name: str, *args, **kwargs):
        """Call a registered callback if it exists."""
        if name in self.callbacks and self.callbacks[name]:
            try:
                self.callbacks[name](*args, **kwargs)
            except Exception as e:
                logger.error(f"Callback {name} error: {e}")

    def print(self, message: str):
        """Print message to UI."""
        self._callback('on_print', message)

    def update_status(self, status: str):
        """Update status in UI."""
        self._callback('on_status', status)

    def change_state(self, state: State) -> None:
        """Update miner state and signal the state machine."""
        # Android-specific: EXIT state is terminal — prevent further changes
        if self.state is not State.EXIT:
            self.state = state
        self._state_change.set()

    def close(self) -> None:
        """Request application exit. Called by task_wrapper on critical failures."""
        # Android-specific: signals the state machine to exit cleanly
        self.change_state(State.EXIT)

    def update_progress(self, current: int, total: int):
        """Update progress in UI."""
        self._callback('on_progress', current, total)

    def update_channel(self, channel_name: str):
        """Update current channel in UI."""
        self._callback('on_channel', channel_name)

    def update_drop(self, drop: Optional[TimedDrop]):
        """Update current drop in UI."""
        self._callback('on_drop', drop)

    def update_inventory(self):
        """Update inventory in UI."""
        self._callback('on_inventory', self.inventory)

    def notify(self, title: str, message: str):
        """Show notification."""
        self._callback('on_notify', title, message)

    # ========================================================================
    # SESSION MANAGEMENT
    # ========================================================================

    def _clean_token(self, token: str) -> str:
        """Strip 'oauth:' prefix from token if present."""
        if token.startswith('oauth:'):
            return token[len('oauth:'):]
        return token

    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            headers = {
                'Client-ID': CLIENT_ID,
                'User-Agent': USER_AGENT,
            }
            if self.settings.oauth_token:
                headers['Authorization'] = f'OAuth {self._clean_token(self.settings.oauth_token)}'

            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def close_session(self):
        """Close aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    @asynccontextmanager
    async def request(self, method: str, url, **kwargs):
        """
        Async context manager for HTTP requests.
        Android-specific: wraps aiohttp session so Channel can call self._twitch.request(...)
        """
        session = await self.get_session()
        async with session.request(method, url, **kwargs) as response:
            yield response

    # ========================================================================
    # GQL REQUESTS
    # ========================================================================

    async def gql_request(self, operation):
        """
        Make a GraphQL request to Twitch.
        Accepts a single operation dict or a list of operation dicts (batch).
        Returns a dict for single requests, or a list of dicts for batch requests.
        """
        session = await self.get_session()

        if isinstance(operation, list):
            payload = [
                {
                    "operationName": op["operationName"],
                    "extensions": op["extensions"],
                    "variables": op.get("variables", {}),
                }
                for op in operation
            ]
        else:
            payload = {
                "operationName": operation["operationName"],
                "extensions": operation["extensions"],
                "variables": operation.get("variables", {}),
            }

        try:
            async with session.post(GQL_URL, json=payload) as response:
                if response.status == 401:
                    raise LoginException("Authentication failed")

                data = await response.json()

                if isinstance(data, list):
                    for item in data:
                        if "errors" in item:
                            raise GQLException(item["errors"][0]["message"])
                    return data
                else:
                    if "errors" in data:
                        raise GQLException(data["errors"][0]["message"])
                    return data
        except aiohttp.ClientError as e:
            raise MinerException(f"Network error: {e}")

    # ========================================================================
    # AUTHENTICATION
    # ========================================================================

    async def login(self) -> bool:
        """Login to Twitch using OAuth token."""
        if not self.settings.oauth_token:
            raise LoginException("No OAuth token provided")

        self.print("Logging in...")
        self.update_status("Logging in...")

        try:
            token = self._clean_token(self.settings.oauth_token)

            session = await self.get_session()
            async with session.get(
                "https://id.twitch.tv/oauth2/validate",
                headers={
                    'Authorization': f'OAuth {token}',
                }
            ) as response:
                if response.status != 200:
                    raise LoginException(f"Token validation failed (HTTP {response.status})")

                data = await response.json()

            if "user_id" not in data or "login" not in data:
                raise LoginException("Invalid token: no user data returned")

            self.settings.user_id = int(data["user_id"])
            self.settings.username = data["login"]
            self.settings.save()

            self._logged_in.set(True)
            self.print(f"Logged in as: {self.settings.username}")
            self.update_status(f"Logged in: {self.settings.username}")
            return True

        except LoginException:
            raise
        except Exception as e:
            self.print(f"Login failed: {e}")
            self.update_status("Login failed")
            raise LoginException(f"Login failed: {e}")

    def is_logged_in(self) -> bool:
        """Check if logged in."""
        return self._logged_in.has_value()

    async def wait_until_login(self):
        """Wait until logged in."""
        await self._logged_in.wait()

    # ========================================================================
    # INVENTORY & CAMPAIGNS
    # ========================================================================

    def _merge_data(self, primary: "JsonType", secondary: "JsonType") -> "JsonType":
        """Merge two JsonType dicts, primary values take precedence."""
        from itertools import chain as _chain
        merged = {}
        for key in set(_chain(primary.keys(), secondary.keys())):
            in_primary = key in primary
            if in_primary and key in secondary:
                vp, vs = primary[key], secondary[key]
                if isinstance(vp, dict) and isinstance(vs, dict):
                    merged[key] = self._merge_data(vp, vs)
                else:
                    merged[key] = vp
            elif in_primary:
                merged[key] = primary[key]
            else:
                merged[key] = secondary[key]
        return merged

    async def fetch_campaigns(
        self, campaigns_chunk: list[tuple[str, "JsonType"]]
    ) -> dict[str, "JsonType"]:
        """Fetch detailed campaign data for a chunk of campaign IDs."""
        campaign_ids: dict[str, "JsonType"] = dict(campaigns_chunk)
        response_list: list["JsonType"] = await self.gql_request([
            GQL_OPERATIONS["CampaignDetails"].with_variables(
                {"channelLogin": str(self.settings.user_id), "dropID": cid}
            )
            for cid in campaign_ids
        ])
        fetched: dict[str, "JsonType"] = {
            (cd := r["data"]["user"]["dropCampaign"])["id"]: cd
            for r in response_list
        }
        return self._merge_data(campaign_ids, fetched)

    async def fetch_inventory(self) -> None:
        """
        Fetch inventory and campaigns using the full upstream 3-step GQL flow.
        # Android-specific: no GUI calls; uses update_status/print callbacks
        """
        self.print("Fetching inventory...")
        self.update_status("Fetching inventory...")
        self.state = State.INVENTORY_FETCH

        # Step 1: fetch in-progress campaigns (inventory)
        response = await self.gql_request(GQL_OPERATIONS["Inventory"])
        inventory_json: "JsonType" = response["data"]["currentUser"]["inventory"]
        ongoing: list["JsonType"] = inventory_json["dropCampaignsInProgress"] or []
        claimed_benefits: dict[str, Any] = {
            b["id"]: timestamp(b["lastAwardedAt"])
            for b in inventory_json["gameEventDrops"]
        }
        inventory_data: dict[str, "JsonType"] = {c["id"]: c for c in ongoing}

        # Step 2: fetch available campaigns
        response = await self.gql_request(GQL_OPERATIONS["Campaigns"])
        available_list: list["JsonType"] = (
            response["data"]["currentUser"]["dropCampaigns"] or []
        )
        available_campaigns: dict[str, "JsonType"] = {
            c["id"]: c
            for c in available_list
            if c["status"] in ("ACTIVE", "UPCOMING")
        }

        # Step 3: fetch campaign details in chunks
        self.update_status("Fetching campaign details...")
        fetch_tasks = [
            asyncio.create_task(self.fetch_campaigns(campaigns_chunk))
            for campaigns_chunk in chunk(list(available_campaigns.items()), 20)
        ]
        try:
            for coro in asyncio.as_completed(fetch_tasks):
                chunk_data = await coro
                inventory_data = self._merge_data(inventory_data, chunk_data)
        except Exception:
            for task in fetch_tasks:
                task.cancel()
            raise

        # Filter invalid campaigns (no game)
        for cid in list(inventory_data.keys()):
            if inventory_data[cid].get("game") is None:
                del inventory_data[cid]

        # Build campaign objects
        campaigns: list[DropsCampaign] = [
            DropsCampaign(self, cdata, claimed_benefits)
            for cdata in inventory_data.values()
        ]
        campaigns.sort(key=lambda c: c.active, reverse=True)
        campaigns.sort(key=lambda c: c.upcoming and c.starts_at or c.ends_at)
        campaigns.sort(key=lambda c: c.eligible, reverse=True)

        # Update internal state
        self._drops.clear()
        self.inventory.clear()
        self._campaigns.clear()
        self._mnt_triggers.clear()

        switch_triggers: set = set()
        next_hour = datetime.now(timezone.utc) + timedelta(hours=1)
        for campaign in campaigns:
            self._drops.update({drop.id: drop for drop in campaign.drops})
            self._campaigns[campaign.id] = campaign
            if campaign.can_earn_within(next_hour):
                switch_triggers.update(campaign.time_triggers)
            self.inventory.append(campaign)

        self._mnt_triggers.extend(sorted(switch_triggers))
        # Trim past triggers
        now = datetime.now(timezone.utc)
        while self._mnt_triggers and self._mnt_triggers[0] <= now:
            self._mnt_triggers.popleft()

        # Restart maintenance task
        if self._mnt_task is not None and not self._mnt_task.done():
            self._mnt_task.cancel()
        self._mnt_task = asyncio.create_task(self._maintenance_task())

        self.print(f"Loaded {len(self.inventory)} campaigns")
        self.update_inventory()
        self.update_status(f"Loaded {len(self.inventory)} campaigns")

    def get_active_campaign(self) -> Optional[DropsCampaign]:
        """Get the currently active campaign to mine."""
        if not self.watching_channel:
            return None

        # Filter campaigns that can be earned on current channel
        available = [c for c in self.inventory if c.can_earn(self.watching_channel)]

        if not available:
            return None

        # Sort by priority mode
        if self.settings.priority_mode == PriorityMode.ENDING_SOONEST:
            available.sort(key=lambda c: c.ends_at)
        elif self.settings.priority_mode == PriorityMode.LOW_AVAILABILITY:
            available.sort(key=lambda c: c.availability)
        else:  # PRIORITY_ONLY
            # Sort by priority list
            def priority_key(campaign):
                try:
                    return self.settings.priority.index(campaign.game.name)
                except ValueError:
                    return 999999
            available.sort(key=priority_key)

        return available[0] if available else None

    @task_wrapper(critical=True)
    async def _maintenance_task(self) -> None:
        """
        Periodic maintenance: triggers CHANNELS_CLEANUP and INVENTORY_FETCH.
        # Android-specific: no GUI progress; uses logger only
        """
        now = datetime.now(timezone.utc)
        next_period = now + timedelta(minutes=30)
        while True:
            now = datetime.now(timezone.utc)
            if now >= next_period:
                break
            next_trigger = next_period
            while self._mnt_triggers and self._mnt_triggers[0] <= next_trigger:
                next_trigger = self._mnt_triggers.popleft()
            logger.log(
                CALL,
                f"Maintenance waiting until: {next_trigger.astimezone().strftime('%X')}"
            )
            await asyncio.sleep((next_trigger - now).total_seconds())
            now = datetime.now(timezone.utc)
            if now >= next_period:
                break
            if next_trigger != next_period:
                logger.log(CALL, "Maintenance: requesting channels cleanup")
                self.change_state(State.CHANNELS_CLEANUP)
        logger.log(CALL, "Maintenance: requesting inventory reload")
        self.change_state(State.INVENTORY_FETCH)

    async def get_live_streams(
        self, game: Game, *, limit: int = 20, drops_enabled: bool = True
    ) -> list[Channel]:
        """Fetch live channels for a game via GQL GameDirectory."""
        filters = ["DROPS_ENABLED"] if drops_enabled else []
        try:
            response = await self.gql_request(
                GQL_OPERATIONS["GameDirectory"].with_variables({
                    "limit": limit,
                    "slug": game.slug,
                    "options": {
                        "includeRestricted": ["SUB_ONLY_LIVE"],
                        "systemFilters": filters,
                    },
                })
            )
        except GQLException as exc:
            raise MinerException(f"Game: {game.slug}") from exc
        if "game" in response["data"]:
            return [
                Channel.from_directory(self, edge["node"], drops_enabled=drops_enabled)
                for edge in response["data"]["game"]["streams"]["edges"]
                if edge["node"]["broadcaster"] is not None
            ]
        return []

    async def bulk_check_online(self, channels: list[Channel]) -> None:
        """
        Batch GQL check for online status of ACL channels.
        # Android-specific: no GUI; uses channel.external_update()
        """
        stream_gql_ops = [channel.stream_gql for channel in channels]
        if not stream_gql_ops:
            return
        acl_streams_map: dict[int, Any] = {}
        stream_tasks = [
            asyncio.create_task(self.gql_request(stream_chunk))
            for stream_chunk in chunk(stream_gql_ops, 20)
        ]
        try:
            for coro in asyncio.as_completed(stream_tasks):
                response_list = await coro
                for resp in response_list:
                    cd = resp["data"]["user"]
                    if cd is not None:
                        acl_streams_map[int(cd["id"])] = cd
        except Exception:
            for task in stream_tasks:
                task.cancel()
            raise
        # Check available drops for online channels
        acl_drops_map: dict[int, list] = {}
        if self.settings.available_drops_check:
            avail_ops = [
                GQL_OPERATIONS["AvailableDrops"].with_variables(
                    {"channelID": str(cid)}
                )
                for cid, cd in acl_streams_map.items()
                if cd["stream"] is not None
            ]
            avail_tasks = [
                asyncio.create_task(self.gql_request(avail_chunk))
                for avail_chunk in chunk(avail_ops, 20)
            ]
            try:
                for coro in asyncio.as_completed(avail_tasks):
                    response_list = await coro
                    for resp in response_list:
                        ai = resp["data"]["channel"]
                        acl_drops_map[int(ai["id"])] = ai["viewerDropCampaigns"] or []
            except Exception:
                for task in avail_tasks:
                    task.cancel()
                raise
        for channel in channels:
            cid = channel.id
            if cid not in acl_streams_map:
                continue
            cd = acl_streams_map[cid]
            if cd["stream"] is None:
                continue
            channel.external_update(cd, acl_drops_map.get(cid, []))

    # ========================================================================
    # CHANNELS
    # ========================================================================

    async def fetch_channels_for_game(self, game: Game, limit: int = 30) -> list[Channel]:
        """Fetch live channels for a game."""
        try:
            operation = GQL_OPERATIONS["GetDirectory"].copy()
            operation["variables"]["slug"] = game.slug
            operation["variables"]["limit"] = limit

            response = await self.gql_request(operation)

            if "data" not in response or "game" not in response["data"]:
                return []

            game_data = response["data"]["game"]
            if not game_data or "streams" not in game_data:
                return []

            channels = []
            for edge in game_data["streams"]["edges"]:
                node = edge["node"]
                if node and node.get("broadcaster"):
                    channel = Channel.from_directory(self, node)
                    channels.append(channel)
                    self.channels[channel.id] = channel

            return channels

        except Exception as e:
            logger.error(f"Error fetching channels for {game.name}: {e}")
            return []

    async def select_channel(self) -> Optional[Channel]:
        """Select best channel to watch."""
        campaign = self.get_active_campaign()

        if not campaign:
            self.print("No active campaigns available")
            return None

        self.print(f"Looking for channels for: {campaign.game.name}")
        channels = await self.fetch_channels_for_game(campaign.game)

        if not channels:
            self.print(f"No live channels found for {campaign.game.name}")
            return None

        # Sort by viewer count (descending)
        channels.sort(key=lambda c: c.viewers, reverse=True)

        return channels[0]

    def on_channel_update(
        self,
        channel: Channel,
        stream_before,
        stream_after,
    ) -> None:
        """
        Called by Channel when its stream status changes.
        Android-specific: triggers UI updates and channel switching logic
        """
        if stream_before is None and stream_after is not None:
            # Channel came online
            logger.info(f"{channel.name} went ONLINE")
            if self.watching_channel is None:
                asyncio.get_event_loop().call_soon(
                    lambda: asyncio.ensure_future(self.switch_channel(channel))
                )
        elif stream_before is not None and stream_after is None:
            # Channel went offline
            logger.info(f"{channel.name} went OFFLINE")
            if self.watching_channel == channel:
                asyncio.get_event_loop().call_soon(
                    lambda: asyncio.ensure_future(self.switch_channel())
                )
        channel.display()

    async def switch_channel(self, channel: Optional[Channel] = None):
        """Switch to a different channel."""
        if channel is None:
            channel = await self.select_channel()

        if channel is None:
            self.watching_channel = None
            self.update_channel("None")
            self.update_drop(None)
            return

        self.watching_channel = channel
        self.update_channel(channel.display_name)
        self.print(f"Watching: {channel.display_name} ({channel.game.name})")

        # Update current drop
        campaign = self.get_active_campaign()
        if campaign:
            self.current_drop = campaign.first_drop
            self.update_drop(self.current_drop)

    # ========================================================================
    # CHANNEL PRIORITY & WATCHING
    # ========================================================================

    def get_priority(self, channel: Channel) -> int:
        """Priority index of channel's game; MAX_INT = not wanted."""
        game = channel.game
        if game is None or game not in self.wanted_games:
            return MAX_INT
        return self.wanted_games.index(game)

    @staticmethod
    def _viewers_key(channel: Channel) -> int:
        viewers = channel.viewers
        return viewers if viewers is not None else -1

    def can_watch(self, channel: Channel) -> bool:
        """True if this channel qualifies as a watching candidate."""
        if not channel.online:
            return False
        for campaign in self.inventory:
            if campaign.can_earn(channel) and (
                channel.game is not None
                and channel.drops_enabled
                and channel.game in self.wanted_games
                or campaign.game.is_special_events()
            ):
                return True
        return False

    def should_switch(self, channel: Channel) -> bool:
        """True if channel is a better watching candidate than current."""
        watching = self.watching_channel.get_with_default(None)
        if watching is None:
            return True
        ch_order = self.get_priority(channel)
        wt_order = self.get_priority(watching)
        return (
            ch_order < wt_order
            or ch_order == wt_order
            and channel.acl_based > watching.acl_based
        )

    def watch(self, channel: Channel, *, update_status: bool = True) -> None:
        """Set the channel being watched."""
        self.watching_channel.set(channel)
        self.update_channel(channel.display_name)
        if update_status:
            self.print(f"Watching: {channel.name}")
            self.update_status(f"Watching: {channel.name}")

    def stop_watching(self) -> None:
        """Stop watching the current channel."""
        self.watching_channel.clear()
        self.update_channel("")
        self.update_drop(None)

    def restart_watching(self) -> None:
        """Interrupt watch sleep to restart immediately."""
        # Android-specific: sets event that _watch_sleep awaits
        self._watching_restart.set()

    # ========================================================================
    # WATCHING & MINING
    # ========================================================================

    # ========================================================================
    # PUBSUB HANDLERS
    # ========================================================================

    @task_wrapper
    async def process_stream_state(self, channel_id: int, message: "JsonType") -> None:
        """Handle PubSub StreamState messages (stream-up, stream-down, viewcount)."""
        msg_type = message["type"]
        channel = self.channels.get(channel_id)
        if channel is None:
            logger.error(f"Stream state change for unknown channel: {channel_id}")
            return
        if msg_type == "viewcount":
            if not channel.online:
                channel.check_online()
            else:
                channel.viewers = message["viewers"]
                channel.display()
        elif msg_type == "stream-down":
            channel.set_offline()
        elif msg_type == "stream-up":
            channel.check_online()
        elif msg_type == "commercial":
            pass  # skip
        else:
            logger.warning(f"Unknown stream state: {msg_type}")

    @task_wrapper
    async def process_stream_update(self, channel_id: int, message: "JsonType") -> None:
        """Handle PubSub StreamUpdate messages (title/game changes)."""
        channel = self.channels.get(channel_id)
        if channel is None:
            logger.error(f"Broadcast settings update for unknown channel: {channel_id}")
            return
        if message["old_game"] != message["game"]:
            logger.info(
                f"Channel update: {channel.name}, game: "
                f"{message['old_game']} -> {message['game']}"
            )
        # Use check_online to delay and coalesce multiple rapid updates
        channel.check_online()

    @task_wrapper
    async def process_drops(self, user_id: int, message: "JsonType") -> None:
        """Handle PubSub User/Drops messages (drop-progress, drop-claim)."""
        msg_type: str = message["type"]
        if msg_type not in ("drop-progress", "drop-claim"):
            return
        drop_id: str = message["data"]["drop_id"]
        drop = self._drops.get(drop_id)
        watching = self.watching_channel.get_with_default(None)
        if msg_type == "drop-claim":
            if drop is None:
                logger.error(f"Drop claim for unknown drop: {drop_id}")
                return
            drop.update_claim(message["data"]["drop_instance_id"])
            campaign = drop.campaign
            await drop.claim()
            drop.display()
            await asyncio.sleep(4)
            if watching is not None:
                for _ in range(8):
                    ctx = await self.gql_request(
                        GQL_OPERATIONS["CurrentDrop"].with_variables(
                            {"channelID": str(watching.id)}
                        )
                    )
                    drop_data = ctx["data"]["currentUser"]["dropCurrentSession"]
                    if drop_data is None or drop_data["dropID"] != drop.id:
                        break
                    await asyncio.sleep(2)
            if campaign.can_earn(watching):
                self.restart_watching()
            else:
                self.change_state(State.INVENTORY_FETCH)
            return
        # drop-progress
        if drop is not None and drop.can_earn(watching):
            drop.update_minutes(message["data"]["current_progress_min"])
            logger.log(
                CALL,
                f"{drop.campaign.game} | {drop.name}: "
                f"{drop.current_minutes}/{drop.required_minutes}"
            )

    @task_wrapper
    async def process_notifications(self, user_id: int, message: "JsonType") -> None:
        """Handle PubSub User/Notifications messages."""
        if message["type"] == "create-notification":
            data = message["data"]["notification"]
            if data["type"] in (
                "user_drop_reward_reminder_notification",
                "quests_viewer_reward_campaign_earned_emote",
            ):
                self.change_state(State.INVENTORY_FETCH)
                await self.gql_request(
                    GQL_OPERATIONS["NotificationsDelete"].with_variables(
                        {"input": {"id": data["id"]}}
                    )
                )

    # ========================================================================
    # WATCHING (continued)
    # ========================================================================

    async def send_watch(self) -> bool:
        """Send watch event via the channel's spade mechanism."""
        if not self.watching_channel:
            return False
        try:
            return await self.watching_channel.send_watch()
        except Exception as e:
            logger.error(f"Error sending watch: {e}")
            return False

    async def _watch_loop(self):
        """Main watching loop."""
        while self._running:
            try:
                if self.watching_channel and self.current_drop:
                    success = await self.send_watch()

                    if success and self.watching_channel and self.current_drop:
                        # Android-specific: bump_minutes handles minute tracking and state transitions
                        self.current_drop.campaign.bump_minutes(self.watching_channel)
                        self.update_drop(self.current_drop)

                await asyncio.sleep(WATCH_INTERVAL.total_seconds())

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in watch loop: {e}")
                await asyncio.sleep(5)

    async def claim_drop(self, drop: TimedDrop):
        """Claim a completed drop."""
        if not drop.claim_id:
            return

        try:
            self.print(f"Claiming drop: {drop.name}")

            operation = GQL_OPERATIONS["ClaimDrop"].copy()
            operation["variables"]["input"]["dropInstanceID"] = drop.claim_id

            response = await self.gql_request(operation)

            if "data" in response:
                drop.is_claimed = True
                self.print(f"✓ Claimed: {drop.name}")
                self.notify("Drop Claimed", f"{drop.name}\n{drop.campaign.game.name}")

        except Exception as e:
            self.print(f"Error claiming drop: {e}")

    # ========================================================================
    # MAIN LOOP
    # ========================================================================

    async def start(self):
        """Start the miner — login, inventory, websocket, watch loop."""
        if self._running:
            return
        self._running = True
        self.print("Starting TwitchDropsMiner...")

        try:
            if not self.is_logged_in():
                await self.login()

            await self.fetch_inventory()

            # Android-specific: renamed from websocket_pool to websocket
            self.websocket = WebsocketPool(self)
            await self.websocket.start()

            # Subscribe to user-level PubSub topics
            user_id = self.settings.user_id
            if user_id:
                self.websocket.add_topics([
                    WebsocketTopic("User", "Drops", user_id, self.process_drops),
                    WebsocketTopic(
                        "User", "Notifications", user_id, self.process_notifications
                    ),
                ])

            self._watch_task = asyncio.create_task(self._watch_loop())
            self.change_state(State.GAMES_UPDATE)

            self.print("Miner started")
            self.update_status("Running")

        except Exception as e:
            self.print(f"Error starting: {e}")
            self.update_status("Error")
            await self.stop()
            raise

    async def stop(self):
        """Stop the miner cleanly."""
        if not self._running:
            return

        self._running = False
        self.print("Stopping miner...")
        self.update_status("Stopping...")

        if self._watch_task:
            self._watch_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._watch_task

        if self._mnt_task:
            self._mnt_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._mnt_task

        if self.websocket:
            await self.websocket.stop(clear_topics=True)

        await self.close_session()
        self.print("Miner stopped")
        self.update_status("Stopped")

    async def restart(self):
        """Restart the miner."""
        await self.stop()
        await asyncio.sleep(2)
        await self.start()
