"""Channel representation"""
from typing import TYPE_CHECKING, Optional
from core.utils import Game

if TYPE_CHECKING:
    from core.twitch_client import TwitchClient


class Channel:
    """Represents a Twitch channel."""

    def __init__(self, twitch: 'TwitchClient', channel_id: int, login: str, display_name: str):
        self._twitch = twitch
        self.id = channel_id
        self.login = login
        self.display_name = display_name
        self.game: Optional[Game] = None
        self.viewers = 0
        self.drops_enabled = False
        self.online = False

    def __str__(self):
        return self.display_name

    def __repr__(self):
        return f"Channel({self.login}, {self.game.name if self.game else 'None'})"

    def __eq__(self, other):
        if isinstance(other, Channel):
            return self.id == other.id
        return False

    def __hash__(self):
        return self.id

    @classmethod
    def from_acl(cls, twitch: 'TwitchClient', data: dict) -> 'Channel':
        """Create a channel from an ACL (allow-list) entry in a drops campaign."""
        return cls(
            twitch,
            int(data["id"]),
            data["name"],
            data.get("displayName") or data["name"],
        )

    @classmethod
    def from_directory(cls, twitch: 'TwitchClient', data: dict) -> 'Channel':
        """Create channel from directory data."""
        broadcaster = data["broadcaster"]
        channel_id = int(broadcaster["id"])
        login = broadcaster["login"]
        display_name = broadcaster["displayName"]

        channel = cls(twitch, channel_id, login, display_name)

        # Parse stream data
        if "game" in data and data["game"]:
            channel.game = Game(data["game"])

        channel.viewers = data.get("viewersCount", 0)
        channel.online = True

        # Check for drops
        # In real implementation, this would check viewerDropCampaigns
        channel.drops_enabled = True

        return channel
