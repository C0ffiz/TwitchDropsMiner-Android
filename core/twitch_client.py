"""Main Twitch client for drops mining"""
import asyncio
import logging
import json
from time import time
from collections import deque, OrderedDict
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
from typing import Optional, Any, NoReturn, TYPE_CHECKING

import aiohttp

from core.constants import (
    CALL, MAX_INT, CLIENT_ID, USER_AGENT, CLIENT_URL, GQL_URL, GQL_OPERATIONS,
    State, PriorityMode, WATCH_INTERVAL, WebsocketTopic, MAX_CHANNELS,
)
from core.exceptions import (
    MinerException, LoginException, GQLException,
)
from core.utils import (
    timestamp, Game, AwaitableValue,
    ExponentialBackoff, RateLimiter, chunk, task_wrapper,
    create_nonce, CHARS_HEX_LOWER,
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
        self.watching_channel: AwaitableValue = AwaitableValue()  # Android-specific: was Optional[Channel]
        self.current_drop: Optional[TimedDrop] = None
        self.games: set[Game] = set()
        self.notifications = _NotificationsShim(self)  # Android-specific

        # Drop tracking (Android-specific: flat dicts for fast lookup)
        self._drops: dict[str, TimedDrop] = {}
        self._campaigns: dict[str, DropsCampaign] = {}

        # Game priority list
        self.wanted_games: list[Game] = []

        # Channels (OrderedDict preserves insertion order; iteration order matters for priority)
        self.channels: OrderedDict[int, Channel] = OrderedDict()

        # Android-specific: renamed from websocket_pool to websocket
        self.websocket: Optional[WebsocketPool] = None

        # Tasks
        self._watch_task: Optional[asyncio.Task] = None
        self._mnt_task: Optional[asyncio.Task] = None  # Android-specific: was _maintenance_task
        self._mnt_triggers: deque = deque()  # Android-specific

        # GQL rate limiter (5 requests per second)
        self._gql_limiter = RateLimiter(capacity=5, window=1)  # Android-specific

        # Auth identity headers — generated once per session, sent with every GQL request.
        # Mirrors upstream _AuthState.device_id / session_id which Twitch checks for integrity.
        self._device_id: str = create_nonce(CHARS_HEX_LOWER, 32)
        self._session_id: str = create_nonce(CHARS_HEX_LOWER, 16)

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
        self.current_drop = drop  # Android-specific: keep current_drop in sync for HomeScreen.on_enter re-sync
        self._callback('on_drop', drop)

    def update_inventory(self):
        """Update inventory in UI."""
        self._callback('on_inventory', self.inventory)

    def update_channels(self) -> None:
        """Update channels in UI."""
        self._callback('on_channels', self.channels)  # Android-specific: push channel dict to ChannelsScreen

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
                'Accept': '*/*',
                'Accept-Encoding': 'gzip, deflate',
                'Accept-Language': 'en-US',
                'Pragma': 'no-cache',
                'Cache-Control': 'no-cache',
                'Client-Id': CLIENT_ID,
                'User-Agent': USER_AGENT,
                'Client-Session-Id': self._session_id,
                'X-Device-Id': self._device_id,
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

    async def gql_request(
        self, ops: "GQLOperation | list[GQLOperation]"
    ) -> "JsonType | list[JsonType]":
        """
        Make a GQL request with exponential backoff retry.
        # Android-specific: uses _gql_limiter; no GUI wait; retries network errors
        """
        backoff = ExponentialBackoff(maximum=60)
        single_retry: bool = True
        max_retries: int = 5  # Android-specific: cap forced retries to avoid infinite loop
        retry_count: int = 0
        # Android-specific: normalize GQLOperation (dict subclass) to plain dict/list
        # so aiohttp's JSON encoder always receives a standard serializable type
        if isinstance(ops, list):
            payload = [dict(o) for o in ops]
        else:
            payload = dict(ops)
        gql_headers: dict = {
            'Origin': CLIENT_URL,
            'Referer': CLIENT_URL,
            'X-Device-Id': self._device_id,
            'Client-Session-Id': self._session_id,
        }
        for delay in backoff:
            async with self._gql_limiter:
                session = await self.get_session()
                logger.debug(f"GQL request payload: {payload}")
                async with session.post(GQL_URL, json=payload, headers=gql_headers) as response:
                    if response.status == 401:
                        raise LoginException("Authentication failed")
                    response_json = await response.json()
            if isinstance(response_json, list):
                response_list = response_json
            else:
                response_list = [response_json]
            force_retry: bool = False
            for item in response_list:
                if "errors" in item:
                    for error_dict in item["errors"]:
                        msg = error_dict.get("message", "")
                        if single_retry and msg in ("service error", "PersistedQueryNotFound"):
                            logger.error(
                                f"Retrying a {msg} for "
                                f"{item.get('extensions', {}).get('operationName', '?')}"
                            )
                            force_retry = True
                            break
                        raise GQLException(msg)
                    if force_retry:
                        break
            if force_retry:
                retry_count += 1
                if retry_count >= max_retries:  # Android-specific: cap retries; ExponentialBackoff never stops
                    raise MinerException("GQL request failed after retries")
                single_retry = False
                continue
            return response_json
        raise MinerException("GQL request failed after retries")

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

            # Verify the token was issued for our current client ID.
            # A mismatch means a stale token from a previous client type (e.g. WEB vs ANDROID_APP).
            # Raising LoginException here causes the caller to fall back to device login.
            token_client_id = data.get("client_id", "")
            if token_client_id and token_client_id != CLIENT_ID:
                raise LoginException(
                    f"Token client mismatch (got {token_client_id}, expected {CLIENT_ID}). "
                    "Please log in again."
                )

            self.settings.user_id = int(data["user_id"])
            self.settings.username = data["login"]
            self.settings.save()

            self._logged_in.set(True)
            self.print(f"Logged in as: {self.settings.username}")
            self.update_status(f"Logged in: {self.settings.username}")

            # Visit the Twitch website to establish a proper cookie session.
            # Mirrors upstream _AuthState._validate() which visits CLIENT_URL and extracts
            # the `unique_id` cookie for use as device_id in X-Device-Id headers.
            # Without a real Twitch-assigned device_id the integrity check fails for
            # some GQL operations (e.g. ViewerDropsDashboard / Campaigns).
            try:
                async with session.get(CLIENT_URL) as page_response:
                    await page_response.read()
                # Extract Twitch-assigned unique_id and use it as device_id
                for cookie in session.cookie_jar:
                    if cookie.key == "unique_id":
                        self._device_id = cookie.value
                        logger.debug("Got Twitch-assigned device_id from cookie")
                        break
            except Exception as e:
                logger.warning(f"Could not establish Twitch cookie session: {e}")

            # Invalidate any stale integrity token so it is re-fetched with
            # the new session/device_id on the first GQL request.
            self._integrity_token = ""

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

    async def start_device_login(self) -> None:
        """
        OAuth device code flow (Phase 7).

        Fires on_login_code(user_code, verification_uri) when a code is obtained,
        then polls id.twitch.tv/oauth2/token every `interval` seconds until the
        user activates the device or the code expires.

        On success: saves oauth_token to settings, validates via login() to fetch
        user_id/username, then fires on_login_success().

        On code expiry: requests a new device code and fires on_login_code again.
        Mirrors upstream _AuthState._oauth_login() without tkinter / gui calls.
        """
        req_headers = {
            "Accept": "application/json",
            "Client-Id": CLIENT_ID,
        }
        device_payload = {
            "client_id": CLIENT_ID,
            "scopes": "",  # no scopes needed
        }

        while True:
            try:
                now = datetime.now(timezone.utc)

                # ---- Step 1: request device code ----
                async with aiohttp.ClientSession() as auth_session:
                    async with auth_session.post(
                        "https://id.twitch.tv/oauth2/device",
                        headers=req_headers,
                        data=device_payload,
                    ) as response:
                        if response.status != 200:
                            raise LoginException(
                                f"Device code request failed (HTTP {response.status})"
                            )
                        data: dict = await response.json()

                device_code: str = data["device_code"]
                user_code: str = data["user_code"]
                interval: int = data["interval"]
                verification_uri: str = data["verification_uri"]
                expires_at = now + timedelta(seconds=data["expires_in"])

                logger.info(
                    f"Device login: user_code={user_code}, "
                    f"expires_in={data['expires_in']}s, interval={interval}s"
                )

                # ---- Step 2: show code in UI ----
                self._callback("on_login_code", user_code, verification_uri)

                token_payload = {
                    "client_id": CLIENT_ID,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                }

                # ---- Step 3: polling loop ----
                # Use a single session for the entire polling sequence.
                async with aiohttp.ClientSession() as auth_session:
                    code_expired = False
                    while not code_expired:
                        # Sleep first — user won't activate that fast.
                        await asyncio.sleep(interval)

                        if datetime.now(timezone.utc) >= expires_at:
                            code_expired = True
                            break

                        async with auth_session.post(
                            "https://id.twitch.tv/oauth2/token",
                            headers=req_headers,
                            data=token_payload,
                        ) as response:
                            if response.status == 400:
                                # authorization_pending — user hasn't entered code yet
                                continue
                            if response.status != 200:
                                logger.warning(
                                    f"Token poll unexpected HTTP {response.status}"
                                )
                                continue
                            token_data: dict = await response.json()

                        # ---- Step 4: success — save token and validate ----
                        self.settings.oauth_token = token_data["access_token"]
                        # Force rebuild of the main session with the new Authorization header.
                        await self.close_session()
                        # Validate token; sets settings.user_id, settings.username, _logged_in.
                        await self.login()
                        self._callback("on_login_success")
                        return

                # Code expired — loop back to request a new one.
                logger.info("Device activation code expired, requesting a new one")
                self.print("Activation code expired. Requesting a new code...")

            except (LoginException, asyncio.CancelledError):
                raise
            except Exception as e:
                logger.error(f"Device login error: {e}")
                self.print(f"Device login error: {e}")
                await asyncio.sleep(5)

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

    def get_active_campaign(
        self, channel: Optional[Channel] = None
    ) -> Optional[DropsCampaign]:
        """
        Get the highest-priority campaign earnable on the given channel.
        # Android-specific: no GUI selection; uses settings.priority_mode
        """
        watching = self.watching_channel.get_with_default(channel)
        if watching is None:
            return None
        available = [c for c in self.inventory if c.can_earn(watching)]
        if not available:
            return None
        priority_mode = self.settings.priority_mode
        priority = self.settings.priority
        if priority_mode == PriorityMode.ENDING_SOONEST:
            available.sort(key=lambda c: c.ends_at)
        elif priority_mode == PriorityMode.LOW_AVAILABILITY:
            available.sort(key=lambda c: c.availability)
        else:  # PRIORITY_ONLY
            available.sort(
                key=lambda c: (
                    priority.index(c.game.name) if c.game.name in priority else MAX_INT
                )
            )
        return available[0]

    @task_wrapper(critical=True)
    async def _maintenance_task(self) -> None:
        """
        Periodic maintenance: triggers CHANNELS_CLEANUP and INVENTORY_FETCH.
        # Android-specific: no GUI progress; uses logger only
        """
        now = datetime.now(timezone.utc)
        next_period = now + timedelta(minutes=5)
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

    def on_channel_update(
        self,
        channel: Channel,
        stream_before,
        stream_after,
    ) -> None:
        """
        Called by Channel when its stream status changes.
        # Android-specific: triggers state machine transitions
        """
        watching = self.watching_channel.get_with_default(None)
        if stream_before is None and stream_after is not None:
            logger.info(f"{channel.name} went ONLINE")
            if watching is None:
                self.change_state(State.CHANNEL_SWITCH)
        elif stream_before is not None and stream_after is None:
            logger.info(f"{channel.name} went OFFLINE")
            if watching is channel:
                self.change_state(State.CHANNEL_SWITCH)
        channel.display()

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
        watching = self.watching_channel.get_with_default(None)
        if watching is None:
            return False
        try:
            return await watching.send_watch()
        except Exception as e:
            logger.error(f"Error sending watch: {e}")
            return False

    async def _watch_sleep(self, delay: float) -> None:
        """Interruptible sleep — ended early if restart_watching() is called."""
        # Android-specific: _watching_restart event replaces GUI-based interrupt
        self._watching_restart.clear()
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._watching_restart.wait(), timeout=delay)

    @task_wrapper(critical=True)
    async def _watch_loop(self) -> NoReturn:
        """
        Main watch loop: sends watch payload every WATCH_INTERVAL seconds,
        with GQL-based minute recovery when PubSub progress stalls.
        # Android-specific: no GUI progress check; uses time-based fallback
        """
        interval: float = WATCH_INTERVAL.total_seconds()
        while True:
            channel: Channel = await self.watching_channel.get()
            if not channel.online:
                self.stop_watching()
                continue
            succeeded: bool = await channel.send_watch()
            last_sent: float = time()
            if not succeeded:
                logger.log(CALL, f"Watch request failed for channel: {channel.name}")
            # wait ~20 seconds for a PubSub progress update
            await asyncio.sleep(20)
            # Android-specific: check for stalled progress using elapsed time
            # rather than GUI progress bar
            handled: bool = False
            try:
                context = await self.gql_request(
                    GQL_OPERATIONS["CurrentDrop"].with_variables(
                        {"channelID": str(channel.id)}
                    )
                )
                drop_data = context["data"]["currentUser"]["dropCurrentSession"]
            except GQLException:
                drop_data = None
            if drop_data is not None:
                gql_drop = self._drops.get(drop_data["dropID"])
                if gql_drop is not None and gql_drop.can_earn(channel):
                    gql_drop.update_minutes(drop_data["currentMinutesWatched"])
                    self.update_drop(gql_drop)
                    logger.log(
                        CALL,
                        f"{gql_drop.campaign.game} | {gql_drop.name}: "
                        f"{gql_drop.current_minutes}/{gql_drop.required_minutes}"
                    )
                    handled = True
            if not handled:
                active_campaign = self.get_active_campaign(channel)
                if active_campaign is not None:
                    active_campaign.bump_minutes(channel)
                    active_drop = active_campaign.first_drop
                    if active_drop is not None:
                        active_drop.display()
                        self.update_drop(active_drop)
                    logger.log(CALL, f"Drop progress from active search: {active_campaign.game}")
                else:
                    logger.log(CALL, "No active drop could be determined")
            await self._watch_sleep(interval - min(time() - last_sent, interval))

    # ========================================================================
    # MAIN LOOP
    # ========================================================================

    @task_wrapper(critical=True)
    async def _run(self) -> None:
        """
        Full upstream state machine.
        # Android-specific: no pystray, no gui.tray, no gui.channels, no translate()
        # All status updates go through self.update_status() and self.print()
        """
        if not self.is_logged_in():
            await self.login()

        self.websocket = WebsocketPool(self)
        await self.websocket.start()

        if self._watch_task is not None:
            self._watch_task.cancel()
        self._watch_task = asyncio.create_task(self._watch_loop())

        user_id = self.settings.user_id
        if user_id:
            self.websocket.add_topics([
                WebsocketTopic("User", "Drops", user_id, self.process_drops),
                WebsocketTopic("User", "Notifications", user_id, self.process_notifications),
            ])

        full_cleanup: bool = False
        channels: OrderedDict[int, Channel] = self.channels
        self.change_state(State.INVENTORY_FETCH)

        while True:
            if self.state is State.IDLE:
                self.update_status("Idle \u2014 no campaigns available")
                self.stop_watching()
                self._state_change.clear()

            elif self.state is State.INVENTORY_FETCH:
                self.update_status("Fetching inventory...")
                await self.websocket.start()
                await self.fetch_inventory()
                self.change_state(State.GAMES_UPDATE)

            elif self.state is State.GAMES_UPDATE:
                # Claim any immediately claimable drops first
                for campaign in self.inventory:
                    if not campaign.upcoming:
                        for drop in campaign.drops:
                            if drop.can_claim:
                                await drop.claim()
                # Rebuild wanted_games from settings + inventory
                self.wanted_games.clear()
                exclude = self.settings.exclude
                priority = self.settings.priority
                priority_mode = self.settings.priority_mode
                next_hour = datetime.now(timezone.utc) + timedelta(hours=1)
                sorted_campaigns = list(self.inventory)
                if priority_mode is PriorityMode.ENDING_SOONEST:
                    primary_key = lambda c: (c.ends_at, MAX_INT)
                elif priority_mode is PriorityMode.LOW_AVAILABILITY:
                    primary_key = lambda c: (c.availability, MAX_INT)
                else:
                    primary_key = lambda c: (
                        priority.index(c.game.name)
                        if c.game.name in priority
                        else MAX_INT
                    )
                sorted_campaigns.sort(key=primary_key)
                for campaign in sorted_campaigns:
                    game = campaign.game
                    if (
                        game not in self.wanted_games
                        and game.name not in exclude
                        and (not priority or game.name in priority)  # Android-specific: empty priority = all games
                        and campaign.eligible
                        and campaign.can_earn_within(next_hour)
                    ):
                        self.wanted_games.append(game)
                full_cleanup = True
                self.restart_watching()
                self.change_state(State.CHANNELS_CLEANUP)

            elif self.state is State.CHANNELS_CLEANUP:
                self.update_status("Cleaning up channels...")
                if not self.wanted_games or full_cleanup:
                    to_remove = list(channels.values())
                else:
                    to_remove = [
                        ch for ch in channels.values()
                        if (
                            not ch.acl_based
                            and (ch.offline or ch.game is None or ch.game not in self.wanted_games)
                        )
                    ]
                full_cleanup = False
                if to_remove:
                    remove_topics = []
                    for ch in to_remove:
                        remove_topics.append(
                            WebsocketTopic.as_str("Channel", "StreamState", ch.id)
                        )
                        remove_topics.append(
                            WebsocketTopic.as_str("Channel", "StreamUpdate", ch.id)
                        )
                    self.websocket.remove_topics(remove_topics)
                    for ch in to_remove:
                        del channels[ch.id]
                        ch.remove()
                if self.wanted_games:
                    self.change_state(State.CHANNELS_FETCH)
                else:
                    self.print("No campaigns available to earn")
                    self.change_state(State.IDLE)

            elif self.state is State.CHANNELS_FETCH:
                self.update_status("Gathering channels...")
                new_channels: set[Channel] = set(channels.values())
                channels.clear()
                no_acl: set = set()
                acl_channels: set[Channel] = set()
                next_hour = datetime.now(timezone.utc) + timedelta(hours=1)
                for campaign in self.inventory:
                    if (
                        campaign.game in self.wanted_games
                        and campaign.can_earn_within(next_hour)
                    ):
                        if campaign.allowed_channels:
                            acl_channels.update(campaign.allowed_channels)
                        else:
                            no_acl.add(campaign.game)
                acl_channels.difference_update(new_channels)
                await self.bulk_check_online(list(acl_channels))
                new_channels.update(acl_channels)
                for game in no_acl:
                    new_channels.update(await self.get_live_streams(game, drops_enabled=True))
                ordered: list[Channel] = sorted(
                    new_channels, key=self._viewers_key, reverse=True
                )
                ordered.sort(key=lambda ch: ch.acl_based, reverse=True)
                ordered.sort(key=self.get_priority)
                trimmed = ordered[MAX_CHANNELS:]
                ordered = ordered[:MAX_CHANNELS]
                if trimmed:
                    trim_topics = []
                    for ch in trimmed:
                        trim_topics.append(
                            WebsocketTopic.as_str("Channel", "StreamState", ch.id)
                        )
                        trim_topics.append(
                            WebsocketTopic.as_str("Channel", "StreamUpdate", ch.id)
                        )
                    self.websocket.remove_topics(trim_topics)
                for ch in ordered:
                    channels[ch.id] = ch
                    ch.display(add=True)
                add_topics: list[WebsocketTopic] = []
                for cid in channels:
                    add_topics.append(
                        WebsocketTopic(
                            "Channel", "StreamState", cid, self.process_stream_state
                        )
                    )
                    add_topics.append(
                        WebsocketTopic(
                            "Channel", "StreamUpdate", cid, self.process_stream_update
                        )
                    )
                self.websocket.add_topics(add_topics)
                # Relink or stop watching
                watching_now = self.watching_channel.get_with_default(None)
                if watching_now is not None:
                    relinked = channels.get(watching_now.id)
                    if relinked is not None and self.can_watch(relinked):
                        self.watch(relinked, update_status=False)
                    else:
                        self.stop_watching()
                # Pre-display active drop
                for ch in channels.values():
                    if self.can_watch(ch):
                        active_campaign = self.get_active_campaign(ch)
                        if active_campaign is not None:
                            active_drop = active_campaign.first_drop
                            if active_drop is not None:
                                active_drop.display(countdown=False, subone=True)
                        break
                self.update_channels()  # Android-specific: push populated channel dict to UI after fetch
                self.change_state(State.CHANNEL_SWITCH)

            elif self.state is State.CHANNEL_SWITCH:
                self.update_status("Switching channel...")
                new_watching: Optional[Channel] = None
                for ch in sorted(channels.values(), key=self.get_priority):
                    if self.can_watch(ch) and self.should_switch(ch):
                        new_watching = ch
                        break
                watching_now = self.watching_channel.get_with_default(None)
                if new_watching is not None:
                    self.watch(new_watching)
                    self._state_change.clear()
                elif watching_now is not None and self.can_watch(watching_now):
                    self.update_status(f"Watching: {watching_now.name}")
                    self._state_change.clear()
                else:
                    self.print("No channel available to watch")
                    self.change_state(State.IDLE)

            elif self.state is State.EXIT:
                self.update_status("Exiting...")
                break

            await self._state_change.wait()

    async def start(self):
        """Launch the miner state machine."""
        if self._running:
            return
        self._running = True
        self.print("Starting TwitchDropsMiner...")
        self.update_status("Starting...")
        try:
            await self.close_session()  # Android-specific: force session rebuild with confirmed token before mining
            await self._run()
        except Exception as e:
            self.print(f"Fatal error: {e}")
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
