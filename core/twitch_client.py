"""Main Twitch client for drops mining"""
import asyncio
import logging
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, Callable, Any

import aiohttp

from core.constants import (
    CLIENT_ID, USER_AGENT, GQL_URL, GQL_OPERATIONS,
    State, PriorityMode, WATCH_INTERVAL
)
from core.exceptions import (
    MinerException, LoginException, GQLException,
    CaptchaRequired, ExitRequest
)
from core.utils import create_nonce, timestamp, Game, AwaitableValue, ExponentialBackoff
from core.settings import Settings
from core.websocket_client import WebsocketPool
from core.inventory import DropsCampaign, TimedDrop
from core.channel import Channel

logger = logging.getLogger("TwitchDrops")


class TwitchClient:
    """Main Twitch client for mining drops."""

    def __init__(self, settings: Settings, callbacks: dict):
        self.settings = settings
        self.callbacks = callbacks

        # State
        self.state = State.IDLE
        self._running = False
        self._session: Optional[aiohttp.ClientSession] = None
        self._logged_in = AwaitableValue()

        # Data
        self.inventory: list[DropsCampaign] = []
        self.channels: dict[str, Channel] = {}
        self.watching_channel: Optional[Channel] = None
        self.current_drop: Optional[TimedDrop] = None
        self.games: set[Game] = set()

        # Websocket
        self.websocket_pool: Optional[WebsocketPool] = None

        # Tasks
        self._watch_task: Optional[asyncio.Task] = None
        self._maintenance_task: Optional[asyncio.Task] = None

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

    # ========================================================================
    # GQL REQUESTS
    # ========================================================================

    async def gql_request(self, operation: dict) -> dict:
        """Make a GraphQL request to Twitch."""
        session = await self.get_session()

        payload = {
            "operationName": operation["operationName"],
            "extensions": operation["extensions"],
            "variables": operation.get("variables", {})
        }

        try:
            async with session.post(GQL_URL, json=payload) as response:
                if response.status == 401:
                    raise LoginException("Authentication failed")

                data = await response.json()

                if "errors" in data:
                    error_msg = data["errors"][0]["message"]
                    raise GQLException(error_msg)

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
                "https://api.twitch.tv/helix/users",
                headers={
                    'Authorization': f'Bearer {token}',
                    'Client-Id': CLIENT_ID,
                }
            ) as response:
                if response.status != 200:
                    raise LoginException(f"Token validation failed (HTTP {response.status})")

                data = await response.json()

            users = data.get("data", [])
            if not users:
                raise LoginException("Invalid token: no user data returned")

            user = users[0]
            self.settings.user_id = int(user["id"])
            self.settings.username = user["login"]
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

    async def fetch_inventory(self):
        """Fetch drops inventory and campaigns."""
        self.print("Fetching inventory...")
        self.update_status("Fetching inventory...")
        self.state = State.INVENTORY_FETCH

        try:
            response = await self.gql_request(GQL_OPERATIONS["GetDropCampaigns"])

            if "data" not in response:
                raise MinerException("Invalid inventory response")

            campaigns_data = response["data"].get("currentUser", {}).get("dropCampaigns", [])

            self.inventory.clear()
            self.games.clear()

            for campaign_data in campaigns_data:
                try:
                    campaign = DropsCampaign(self, campaign_data)
                    self.inventory.append(campaign)
                    self.games.add(campaign.game)
                except Exception as e:
                    logger.error(f"Error parsing campaign: {e}")

            self.print(f"Found {len(self.inventory)} campaigns")
            self.update_inventory()
            self.update_status(f"Loaded {len(self.inventory)} campaigns")

        except Exception as e:
            self.print(f"Error fetching inventory: {e}")
            raise

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
                    self.channels[channel.login] = channel

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
    # WATCHING & MINING
    # ========================================================================

    async def send_watch(self) -> bool:
        """Send watch event to progress drops."""
        if not self.watching_channel:
            return False

        try:
            # Simulate watching by sending minute watched
            # In real implementation, this would send proper spade events
            return True
        except Exception as e:
            logger.error(f"Error sending watch: {e}")
            return False

    async def watch_loop(self):
        """Main watching loop."""
        while self._running:
            try:
                if self.watching_channel and self.current_drop:
                    success = await self.send_watch()

                    if success:
                        # Update progress (simulated)
                        if self.current_drop:
                            self.current_drop.current_minutes += 1
                            self.update_drop(self.current_drop)

                            # Check if drop is complete
                            if self.current_drop.is_complete:
                                await self.claim_drop(self.current_drop)
                                await self.switch_channel()

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
        """Start the miner."""
        if self._running:
            return

        self._running = True
        self.print("Starting TwitchDropsMiner...")

        try:
            # Login
            if not self.is_logged_in():
                await self.login()

            # Fetch inventory
            await self.fetch_inventory()

            # Start websocket
            self.websocket_pool = WebsocketPool(self)
            await self.websocket_pool.start()

            # Select initial channel
            await self.switch_channel()

            # Start watch loop
            self._watch_task = asyncio.create_task(self.watch_loop())

            self.print("Miner started successfully")
            self.update_status("Running")

        except Exception as e:
            self.print(f"Error starting miner: {e}")
            self.update_status("Error")
            await self.stop()
            raise

    async def stop(self):
        """Stop the miner."""
        if not self._running:
            return

        self._running = False
        self.print("Stopping miner...")
        self.update_status("Stopping...")

        # Cancel tasks
        if self._watch_task:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass

        # Stop websocket
        if self.websocket_pool:
            await self.websocket_pool.stop()

        # Close session
        await self.close_session()

        self.print("Miner stopped")
        self.update_status("Stopped")

    async def restart(self):
        """Restart the miner."""
        await self.stop()
        await asyncio.sleep(2)
        await self.start()
