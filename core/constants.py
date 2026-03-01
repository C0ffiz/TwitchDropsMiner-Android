"""Constants for TwitchDropsMiner Android"""
from __future__ import annotations

import random
import logging
from copy import deepcopy

# Logging special level (mirrors upstream)
CALL: int = logging.INFO - 1
logging.addLevelName(CALL, "CALL")

from enum import Enum, auto
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, Literal, NewType, TYPE_CHECKING

if TYPE_CHECKING:
    from collections import abc  # noqa
    from typing_extensions import TypeAlias

from core.version import VERSION, __version__

# ---------------------------------------------------------------------------
# Custom logging level — must be registered before any logger uses it
# ---------------------------------------------------------------------------
CALL: int = logging.INFO - 1
logging.addLevelName(CALL, "CALL")

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
JsonType = Dict[str, Any]
URLType = NewType("URLType", str)
TopicProcess: TypeAlias = "abc.Callable[[int, JsonType], Any]"

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _merge_vars(base_vars: JsonType, vars: JsonType) -> None:
    """Merge `vars` into `base_vars` in place. Ellipsis marks an unset slot."""
    for k, v in vars.items():
        if k not in base_vars:
            base_vars[k] = v
        elif isinstance(v, dict):
            if isinstance(base_vars[k], dict):
                _merge_vars(base_vars[k], v)
            elif base_vars[k] is Ellipsis:
                base_vars[k] = v
            else:
                raise RuntimeError(f"Var is a dict, base is not: '{k}'")
        elif isinstance(base_vars[k], dict):
            raise RuntimeError(f"Base is a dict, var is not: '{k}'")
        else:
            base_vars[k] = v
    for k, v in base_vars.items():
        if v is Ellipsis:
            raise RuntimeError(f"Unspecified variable: '{k}'")

# ---------------------------------------------------------------------------
# Scalar limits and counts
# ---------------------------------------------------------------------------
MAX_INT = 2**31 - 1          # Android-specific: bounded to 32-bit signed max
MAX_EXTRA_MINUTES = 15
BASE_TOPICS = 2
MAX_WEBSOCKETS = 8           # matches upstream; fewer connections conserves Android battery
WS_TOPICS_LIMIT = 50
TOPICS_PER_CHANNEL = 2
MAX_TOPICS = (MAX_WEBSOCKETS * WS_TOPICS_LIMIT) - BASE_TOPICS
MAX_CHANNELS = MAX_TOPICS // TOPICS_PER_CHANNEL

# Misc
DEFAULT_LANG = "English"

# ---------------------------------------------------------------------------
# Intervals and delays  (corrected to match upstream values)
# ---------------------------------------------------------------------------
PING_INTERVAL = timedelta(minutes=3)    # upstream value (was 4 min — corrected)
PING_TIMEOUT = timedelta(seconds=10)
ONLINE_DELAY = timedelta(seconds=120)
WATCH_INTERVAL = timedelta(seconds=59)  # upstream value: matches Twitch's 1-min drop window (was 20s)
# Android-specific: slower polling when the app is backgrounded
BACKGROUND_WATCH_INTERVAL = timedelta(seconds=120)  # Android-specific

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
GQL_URL = "https://gql.twitch.tv/gql"
WS_URL = "wss://pubsub-edge.twitch.tv/v1"

# ---------------------------------------------------------------------------
# Application identity
# ---------------------------------------------------------------------------
# Android-specific: replaces desktop's WINDOW_TITLE
APP_TITLE: str = f"TwitchDropsMiner v{VERSION}"              # Android-specific
# Android-specific: notification channel ID required for Android 8+
ANDROID_NOTIFICATION_CHANNEL_ID: str = "twitch_drops_miner"  # Android-specific

# ---------------------------------------------------------------------------
# Logging formatters
# ---------------------------------------------------------------------------
LOGGING_LEVELS = {
    0: logging.ERROR,
    1: logging.WARNING,
    2: logging.INFO,
    3: CALL,
    4: logging.DEBUG,
}
FILE_FORMATTER = logging.Formatter(
    "{asctime}.{msecs:03.0f}:\t{levelname:>7}:\t{message}",
    style='{',
    datefmt="%Y-%m-%d %H:%M:%S",
)
OUTPUT_FORMATTER = logging.Formatter("{levelname}: {message}", style='{', datefmt="%H:%M:%S")

# ---------------------------------------------------------------------------
# Android path factory                                               Android-specific
# ---------------------------------------------------------------------------
# Path constants cannot be defined at module import time because App.user_data_dir
# is only available after the Kivy App is initialized.  Call get_app_paths() from
# on_start() or later — never at module level.
def get_app_paths() -> dict[str, Path]:  # Android-specific
    """
    Return a dict of runtime data paths rooted in Android's user_data_dir.

    Must be called AFTER ``App.get_running_app()`` returns a non-None value
    (i.e. from ``on_start`` or any screen callback).  On a desktop dev machine
    without Kivy it falls back to a temp directory so unit tests can run.
    """
    try:
        from kivy.app import App  # type: ignore[import]
        app = App.get_running_app()
        if app is None:
            raise RuntimeError("Kivy App not initialized — call get_app_paths() after on_start")
        base = Path(app.user_data_dir)
    except (ImportError, RuntimeError):
        import tempfile
        base = Path(tempfile.gettempdir()) / "twitchdropsminer"
    return {
        "data_dir": base,
        "log":      base / "twitch_drops.log",
        "cookies":  base / "cookies.jar",
        "settings": base / "settings.json",
        "cache":    base / "cache",
        "dump":     base / "dump.dat",
    }

# ---------------------------------------------------------------------------
# ClientInfo / ClientType
# ---------------------------------------------------------------------------
# Android-specific: CLIENT_URL is stored as str rather than yarl.URL to keep
# this module importable without yarl at module level (aiohttp brings it
# transitively, but not every import context guarantees that).

class ClientInfo:
    def __init__(self, client_url: str, client_id: str, user_agents: str | list[str]) -> None:
        self.CLIENT_URL: str = client_url
        self.CLIENT_ID: str = client_id
        self.USER_AGENT: str
        if isinstance(user_agents, list):
            self.USER_AGENT = random.choice(user_agents)
        else:
            self.USER_AGENT = user_agents

    def __iter__(self):
        return iter((self.CLIENT_URL, self.CLIENT_ID, self.USER_AGENT))


class ClientType:
    WEB = ClientInfo(
        "https://www.twitch.tv",
        "kimne78kx3ncx6brgo4mv6wki5h1ko",
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
        ),
    )
    MOBILE_WEB = ClientInfo(
        "https://m.twitch.tv",
        "r8s4dac0uhzifbpu9sjdiwzctle17ff",
        [
            (
                "Mozilla/5.0 (Linux; Android 16) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/138.0.7204.158 Mobile Safari/537.36"
            ),
            (
                "Mozilla/5.0 (Linux; Android 16; SM-A205U) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/138.0.7204.158 Mobile Safari/537.36"
            ),
            (
                "Mozilla/5.0 (Linux; Android 16; SM-A102U) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/138.0.7204.158 Mobile Safari/537.36"
            ),
            (
                "Mozilla/5.0 (Linux; Android 16; SM-G960U) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/138.0.7204.158 Mobile Safari/537.36"
            ),
            (
                "Mozilla/5.0 (Linux; Android 16; SM-N960U) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/138.0.7204.158 Mobile Safari/537.36"
            ),
            (
                "Mozilla/5.0 (Linux; Android 16; LM-Q720) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/138.0.7204.158 Mobile Safari/537.36"
            ),
            (
                "Mozilla/5.0 (Linux; Android 16; LM-X420) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/138.0.7204.158 Mobile Safari/537.36"
            ),
        ],
    )
    ANDROID_APP = ClientInfo(
        "https://www.twitch.tv",
        "kd1unb4b3q4t58fwlpcbzcbnm76a8fp",
        [
            (
                "Dalvik/2.1.0 (Linux; U; Android 16; SM-S911B Build/TP1A.220624.014) "
                "tv.twitch.android.app/25.3.0/2503006"
            ),
            (
                "Dalvik/2.1.0 (Linux; U; Android 16; SM-S938B Build/BP2A.250605.031) "
                "tv.twitch.android.app/25.3.0/2503006"
            ),
            (
                "Dalvik/2.1.0 (Linux; Android 16; SM-X716N Build/UP1A.231005.007) "
                "tv.twitch.android.app/25.3.0/2503006"
            ),
            (
                "Dalvik/2.1.0 (Linux; U; Android 15; SM-G990B Build/AP3A.240905.015.A2) "
                "tv.twitch.android.app/25.3.0/2503006"
            ),
            (
                "Dalvik/2.1.0 (Linux; U; Android 15; SM-G970F Build/AP3A.241105.008) "
                "tv.twitch.android.app/25.3.0/2503006"
            ),
            (
                "Dalvik/2.1.0 (Linux; U; Android 15; SM-A566E Build/AP3A.240905.015.A2) "
                "tv.twitch.android.app/25.3.0/2503006"
            ),
            (
                "Dalvik/2.1.0 (Linux; U; Android 14; SM-X306B Build/UP1A.231005.007) "
                "tv.twitch.android.app/25.3.0/2503006"
            ),
        ],
    )
    SMARTBOX = ClientInfo(
        "https://android.tv.twitch.tv",
        "ue6666qo983tsx6so1t0vnawi233wa",
        (
            "Mozilla/5.0 (Linux; Android 7.1; Smart Box C1) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
        ),
    )


# Android-specific: this application authenticates as the Twitch Android app client
DEFAULT_CLIENT_TYPE: ClientInfo = ClientType.ANDROID_APP  # Android-specific

# Backward-compatible shims — kept so existing code importing CLIENT_ID / USER_AGENT
# directly continues to work until it is updated to use DEFAULT_CLIENT_TYPE.
CLIENT_ID: str = DEFAULT_CLIENT_TYPE.CLIENT_ID   # Android-specific: shim
USER_AGENT: str = DEFAULT_CLIENT_TYPE.USER_AGENT  # Android-specific: shim

# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

class State(Enum):
    IDLE = auto()
    INVENTORY_FETCH = auto()
    GAMES_UPDATE = auto()
    CHANNELS_FETCH = auto()
    CHANNELS_CLEANUP = auto()
    CHANNEL_SWITCH = auto()
    CHANNEL_ONLINE = auto()  # Android-specific: handles a channel going live mid-session
    EXIT = auto()

# ---------------------------------------------------------------------------
# Priority modes
# ---------------------------------------------------------------------------

class PriorityMode(Enum):
    PRIORITY_ONLY = 0
    ENDING_SOONEST = 1
    LOW_AVBL_FIRST = 2
    LOW_AVAILABILITY = 2  # Android-specific: alias for LOW_AVBL_FIRST (backward compat)

# ---------------------------------------------------------------------------
# GQLOperation class
# ---------------------------------------------------------------------------

class GQLOperation(JsonType):
    def __init__(self, name: str, sha256: str, *, variables: JsonType | None = None):
        super().__init__(
            operationName=name,
            extensions={
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": sha256,
                }
            },
        )
        if variables is not None:
            self.__setitem__("variables", variables)

    def with_variables(self, variables: JsonType) -> GQLOperation:
        modified = deepcopy(self)
        if "variables" in self:
            existing_variables: JsonType = modified["variables"]
            _merge_vars(existing_variables, variables)
        else:
            modified["variables"] = variables
        return modified

# ---------------------------------------------------------------------------
# GQL operations  (hashes updated to upstream values)
# ---------------------------------------------------------------------------

GQL_OPERATIONS: dict[str, GQLOperation] = {
    # returns stream information for a particular channel
    "GetStreamInfo": GQLOperation(
        "VideoPlayerStreamInfoOverlayChannel",
        "198492e0857f6aedead9665c81c5a06d67b25b58034649687124083ff288597d",
        variables={
            "channel": ...,  # channel login
        },
    ),
    # can be used to claim channel points
    "ClaimCommunityPoints": GQLOperation(
        "ClaimCommunityPoints",
        "46aaeebe02c99afdf4fc97c7c0cba964124bf6b0af229395f1f6d1feed05b3d0",
        variables={
            "input": {
                "claimID": ...,   # points claim_id
                "channelID": ..., # channel ID as a str
            },
        },
    ),
    # can be used to claim a drop
    "ClaimDrop": GQLOperation(
        "DropsPage_ClaimDropRewards",
        "a455deea71bdc9015b78eb49f4acfbce8baa7ccbedd28e549bb025bd0f751930",
        variables={
            "input": {
                "dropInstanceID": ...,  # drop claim_id
            },
        },
    ),
    # returns current state of points (balance, claim available) for a particular channel
    "ChannelPointsContext": GQLOperation(
        "ChannelPointsContext",
        "374314de591e69925fce3ddc2bcf085796f56ebb8cad67a0daa3165c03adc345",
        variables={
            "channelLogin": ...,  # channel login
        },
    ),
    # returns all in-progress campaigns
    "Inventory": GQLOperation(
        "Inventory",
        "d86775d0ef16a63a33ad52e80eaff963b2d5b72fada7c991504a57496e1d8e4b",
        variables={
            "fetchRewardCampaigns": False,
        },
    ),
    # returns current state of drops (current drop progress)
    "CurrentDrop": GQLOperation(
        "DropCurrentSessionContext",
        "4d06b702d25d652afb9ef835d2a550031f1cf762b193523a92166f40ea3d142b",
        variables={
            "channelID": ...,    # watched channel ID as a str
            "channelLogin": "",  # always empty string
        },
    ),
    # returns all available campaigns
    "Campaigns": GQLOperation(
        "ViewerDropsDashboard",
        "5a4da2ab3d5b47c9f9ce864e727b2cb346af1e3ea8b897fe8f704a97ff017619",
        variables={
            "fetchRewardCampaigns": False,
        },
    ),
    # returns extended information about a particular campaign
    "CampaignDetails": GQLOperation(
        "DropCampaignDetails",
        "039277bf98f3130929262cc7c6efd9c141ca3749cb6dca442fc8ead9a53f77c1",
        variables={
            "channelLogin": ...,  # user login
            "dropID": ...,        # campaign ID
        },
    ),
    # returns drops available for a particular channel
    "AvailableDrops": GQLOperation(
        "DropsHighlightService_AvailableDrops",
        "782dad0f032942260171d2d80a654f88bdd0c5a9dddc392e9bc92218a0f42d20",
        variables={
            "channelID": ...,  # channel ID as a str
        },
    ),
    # returns stream playback access token
    "PlaybackAccessToken": GQLOperation(
        "PlaybackAccessToken",
        "ed230aa1e33e07eebb8928504583da78a5173989fadfb1ac94be06a04f3cdbe9",
        variables={
            "isLive": True,
            "isVod": False,
            "login": ...,       # channel login
            "platform": "web",
            "playerType": "site",
            "vodID": "",
        },
    ),
    # returns live channels for a particular game
    "GameDirectory": GQLOperation(
        "DirectoryPage_Game",
        "76cb069d835b8a02914c08dc42c421d0dafda8af5b113a3f19141824b901402f",
        variables={
            "limit": 30,  # limit of channels returned
            "slug": ...,  # game slug
            "imageWidth": 50,
            "includeCostreaming": False,
            "options": {
                "broadcasterLanguages": [],
                "freeformTags": None,
                "includeRestricted": ["SUB_ONLY_LIVE"],
                "recommendationsContext": {"platform": "web"},
                "sort": "RELEVANCE",  # also accepted: "VIEWER_COUNT"
                "systemFilters": [],
                "tags": [],
                "requestID": "JIRA-VXP-2397",
            },
            "sortTypeIsRecency": False,
        },
    ),
    "SlugRedirect": GQLOperation(  # can be used to turn game name -> game slug
        "DirectoryGameRedirect",
        "1f0300090caceec51f33c5e20647aceff9017f740f223c3c532ba6fa59f6b6cc",
        variables={
            "name": ...,  # game name
        },
    ),
    "NotificationsView": GQLOperation(  # unused; triggers notifications "update-summary"
        "OnsiteNotifications_View",
        "e8e06193f8df73d04a1260df318585d1bd7a7bb447afa058e52095513f2bfa4f",
        variables={
            "input": {},
        },
    ),
    "NotificationsList": GQLOperation(  # unused
        "OnsiteNotifications_ListNotifications",
        "11cdb54a2706c2c0b2969769907675680f02a6e77d8afe79a749180ad16bfea6",
        variables={
            "cursor": "",
            "displayType": "VIEWER",
            "language": "en",
            "limit": 10,
            "shouldLoadLastBroadcast": False,
        },
    ),
    "NotificationsDelete": GQLOperation(
        "OnsiteNotifications_DeleteNotification",
        "13d463c831f28ffe17dccf55b3148ed8b3edbbd0ebadd56352f1ff0160616816",
        variables={
            "input": {
                "id": "",  # ID of the notification to delete
            },
        },
    ),
}

# Android-specific: legacy aliases used by twitch_client.py before names were aligned
GQL_OPERATIONS["GetDropCampaigns"] = GQL_OPERATIONS["Campaigns"]   # Android-specific: alias
GQL_OPERATIONS["GetInventory"] = GQL_OPERATIONS["Inventory"]        # Android-specific: alias
GQL_OPERATIONS["GetDirectory"] = GQL_OPERATIONS["GameDirectory"]    # Android-specific: alias

# ---------------------------------------------------------------------------
# WebsocketTopic
# ---------------------------------------------------------------------------

class WebsocketTopic:
    def __init__(
        self,
        category: Literal["User", "Channel"],
        topic_name: str,
        target_id: int,
        process: TopicProcess,
    ):
        assert isinstance(target_id, int)
        self._id: str = self.as_str(category, topic_name, target_id)
        self._target_id = target_id
        self._process: TopicProcess = process

    @classmethod
    def as_str(
        cls, category: Literal["User", "Channel"], topic_name: str, target_id: int
    ) -> str:
        return f"{WEBSOCKET_TOPICS[category][topic_name]}.{target_id}"

    def __call__(self, message: JsonType):
        return self._process(self._target_id, message)

    def __str__(self) -> str:
        return self._id

    def __repr__(self) -> str:
        return f"Topic({self._id})"

    def __eq__(self, other) -> bool:
        if isinstance(other, WebsocketTopic):
            return self._id == other._id
        elif isinstance(other, str):
            return self._id == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.__class__.__name__, self._id))

# ---------------------------------------------------------------------------
# Websocket topic name mapping
# ---------------------------------------------------------------------------

WEBSOCKET_TOPICS: dict[str, dict[str, str]] = {
    "User": {  # Using user_id
        "Presence": "presence",                          # unused
        "Drops": "user-drop-events",
        "Notifications": "onsite-notifications",
        "CommunityPoints": "community-points-user-v1",
    },
    "Channel": {  # Using channel_id
        "Drops": "channel-drop-events",                  # unused
        "StreamState": "video-playback-by-id",
        "StreamUpdate": "broadcast-settings-update",
        "CommunityPoints": "community-points-channel-v1",  # unused
    },
}
