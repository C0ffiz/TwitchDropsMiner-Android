"""Utility functions and classes"""
from __future__ import annotations

import io
import os
import re
import json
import random
import string
import asyncio
import logging
import traceback
from enum import Enum
from pathlib import Path
from functools import wraps, cached_property
from contextlib import suppress
from collections import abc, OrderedDict
from datetime import datetime, timezone
from typing import Any, Literal, Callable, Generic, Mapping, TypeVar, ParamSpec, cast

try:
    from yarl import URL as _URL  # optional; aiohttp brings it transitively
    _HAS_YARL = True
except ImportError:  # Android build without yarl installed yet
    _URL = None  # type: ignore[assignment,misc]
    _HAS_YARL = False

from core.exceptions import ExitRequest, ReloadRequest
from core.constants import JsonType, PriorityMode

_T = TypeVar("_T")        # generic type
_D = TypeVar("_D")        # default type
_P = ParamSpec("_P")      # callable params
_JSON_T = TypeVar("_JSON_T", bound=Mapping[Any, Any])

logger = logging.getLogger("TwitchDrops")

# ---------------------------------------------------------------------------
# Named character sets (used by create_nonce and auth code)
# ---------------------------------------------------------------------------
CHARS_ASCII = string.ascii_letters + string.digits
CHARS_HEX_LOWER = string.digits + "abcdef"
CHARS_HEX_UPPER = string.digits + "ABCDEF"


# ---------------------------------------------------------------------------
# Async utilities
# ---------------------------------------------------------------------------

async def first_to_complete(coros: abc.Iterable[abc.Coroutine[Any, Any, _T]]) -> _T:
    tasks = [asyncio.ensure_future(coro) for coro in coros]
    done: set[asyncio.Task[Any]]
    pending: set[asyncio.Task[Any]]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    return await next(iter(done))


# ---------------------------------------------------------------------------
# General utilities
# ---------------------------------------------------------------------------

def chunk(to_chunk: abc.Iterable[_T], chunk_length: int) -> abc.Generator[list[_T], None, None]:
    list_to_chunk = list(to_chunk)
    for i in range(0, len(list_to_chunk), chunk_length):
        yield list_to_chunk[i:i + chunk_length]


def format_traceback(exc: BaseException, **kwargs: Any) -> str:
    """
    Like `traceback.print_exc` but returns a string. Uses the passed-in exception.
    Any additional `**kwargs` are passed to the underlaying `traceback.format_exception`.
    """
    return ''.join(traceback.format_exception(type(exc), exc, **kwargs))


def create_nonce(chars: str, length: int) -> str:
    """Generate a random nonce string."""
    return ''.join(random.choices(chars, k=length))


def timestamp(string: str) -> datetime:
    """Parse an ISO-8601 UTC timestamp string into an aware datetime."""
    try:
        return datetime.strptime(string, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.strptime(string, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def json_minify(data: JsonType | list[JsonType]) -> str:
    """Returns minified JSON for payload usage."""
    return json.dumps(data, separators=(',', ':'))


def deduplicate(iterable: abc.Iterable[_T]) -> list[_T]:
    return list(OrderedDict.fromkeys(iterable).keys())


def invalidate_cache(instance: Any, *attrnames: str) -> None:
    """Invalidate one or more `functools.cached_property` attributes."""
    for name in attrnames:
        with suppress(AttributeError):
            delattr(instance, name)


# ---------------------------------------------------------------------------
# lock_file  (Android-specific stub)
# ---------------------------------------------------------------------------

def lock_file(path: Path) -> tuple[bool, io.TextIOWrapper]:  # Android-specific
    """
    Android apps run in a sandboxed single-process environment, so file-level
    locking via fcntl/msvcrt is both unavailable and unnecessary.
    This stub always reports success so callers don't need an Android-specific
    code path.
    """
    file = path.open('w', encoding="utf8")
    file.write('ツ')
    file.flush()
    return True, file


# ---------------------------------------------------------------------------
# webopen  (Android-specific replacement)
# ---------------------------------------------------------------------------

def webopen(url: Any) -> None:  # Android-specific
    """
    Open a URL in the device browser.

    On Android, uses android.intent via Kivy's UrlRequest or the platform
    Intent mechanism. Falls back to Python's webbrowser module for desktop
    testing and CI.

    Note: A future improvement would be to open an in-app WebView via
    `App.get_running_app().open_webview(url)` for a smoother UX. That would
    require a Kivy WebView widget or the android.webview p4a recipe.
    """
    url_str = str(url)
    try:
        # Android: open in the default system browser via Intent
        from android import mActivity  # type: ignore[import]
        from jnius import autoclass  # type: ignore[import]
        Intent = autoclass("android.content.Intent")
        Uri = autoclass("android.net.Uri")
        intent = Intent(Intent.ACTION_VIEW, Uri.parse(url_str))
        mActivity.startActivity(intent)
    except ImportError:
        # Desktop fallback (dev machine / CI)
        import webbrowser
        webbrowser.open_new_tab(url_str)


# ---------------------------------------------------------------------------
# task_wrapper decorator
# ---------------------------------------------------------------------------

def task_wrapper(
    afunc: abc.Callable[_P, abc.Coroutine[Any, Any, _T]] | None = None,
    *,
    critical: bool = False,
):
    def decorator(
        afunc: abc.Callable[_P, abc.Coroutine[Any, Any, _T]]
    ) -> abc.Callable[_P, abc.Coroutine[Any, Any, _T]]:
        @wraps(afunc)
        async def wrapper(*args: _P.args, **kwargs: _P.kwargs):
            try:
                await afunc(*args, **kwargs)
            except (ExitRequest, ReloadRequest):
                pass
            except Exception:
                logger.exception(f"Exception in {afunc.__name__} task")
                if critical:
                    # Android-specific: import path uses core.twitch_client.TwitchClient
                    # (upstream uses `from twitch import Twitch` — cyclic desktop import)
                    from core.twitch_client import TwitchClient  # Android-specific
                    probe = args and args[0] or None
                    if isinstance(probe, TwitchClient):
                        probe.close()
                    elif probe is not None:
                        probe = getattr(probe, "_twitch", None)
                        if isinstance(probe, TwitchClient):
                            probe.close()
                raise
        return wrapper
    if afunc is None:
        return decorator
    return decorator(afunc)


# ---------------------------------------------------------------------------
# JSON serialization/deserialization helpers
# ---------------------------------------------------------------------------

def _serialize(obj: Any) -> Any:
    d: int | str | float | list[Any] | JsonType
    if isinstance(obj, datetime):
        if obj.tzinfo is None:
            obj = obj.replace(tzinfo=timezone.utc)
        d = obj.timestamp()
    elif isinstance(obj, set):
        d = list(obj)
    elif isinstance(obj, Enum):
        d = obj.value
    elif _HAS_YARL and isinstance(obj, _URL):
        d = str(obj)
    else:
        raise TypeError(obj)
    return {
        "__type": type(obj).__name__,
        "data": d,
    }


_MISSING = object()

SERIALIZE_ENV: dict[str, Callable[[Any], object]] = {
    "set": set,
    "PriorityMode": PriorityMode,
    "datetime": lambda d: datetime.fromtimestamp(d, timezone.utc),
}
if _HAS_YARL:
    SERIALIZE_ENV["URL"] = _URL  # type: ignore[assignment]


def _remove_missing(obj: JsonType) -> JsonType:
    for key, value in obj.copy().items():
        if value is _MISSING:
            del obj[key]
        elif isinstance(value, dict):
            _remove_missing(value)
            if not value:
                del obj[key]
    return obj


def _deserialize(obj: JsonType) -> Any:
    if "__type" in obj:
        obj_type = obj["__type"]
        if obj_type in SERIALIZE_ENV:
            return SERIALIZE_ENV[obj_type](obj["data"])
        else:
            return _MISSING
    return obj


def merge_json(obj: JsonType, template: Mapping[Any, Any]) -> None:
    """Merge `obj` in place to match the keys and types of `template`."""
    for k, v in list(obj.items()):
        if k not in template:
            del obj[k]
        elif type(v) is not type(template[k]):
            obj[k] = template[k]
        elif isinstance(v, dict):
            assert isinstance(template[k], dict)
            merge_json(v, template[k])
    for k in template.keys():
        if k not in obj:
            obj[k] = template[k]


def notification_urls(
    value: str | abc.Iterable[str],
    *,
    mode: Literal["list", "set", "str"] = "list",
) -> list[str] | set[str] | str:
    if isinstance(value, str):
        entries: list[str] = []
        for line in value.replace("\r", "").split("\n"):
            entries.extend(line.split(","))
        normalized = [entry.strip() for entry in entries if entry.strip()]
    else:
        normalized = [str(entry).strip() for entry in value if str(entry).strip()]
    if mode == "list":
        return normalized
    if mode == "set":
        return set(normalized)
    if mode == "str":
        return ", ".join(sorted(set(normalized)))
    raise ValueError(f"Unsupported mode: {mode}")


def json_load(path: Path, defaults: _JSON_T, *, merge: bool = True) -> _JSON_T:
    defaults_dict: JsonType = dict(defaults)
    if path.exists():
        with open(path, 'r', encoding="utf8") as file:
            combined: JsonType = _remove_missing(json.load(file, object_hook=_deserialize))
        if merge:
            merge_json(combined, defaults_dict)
    else:
        combined = defaults_dict
    return cast(_JSON_T, combined)


def json_save(path: Path, contents: Mapping[Any, Any], *, sort: bool = False) -> None:
    try:
        with open(path, 'w', encoding="utf8") as file:
            json.dump(contents, file, default=_serialize, sort_keys=sort, indent=4)
    except OSError as e:
        logger.warning(f"Failed to save {path}: {e}")


# ---------------------------------------------------------------------------
# ExponentialBackoff
# ---------------------------------------------------------------------------

class ExponentialBackoff:
    """
    Iterator that yields exponentially increasing delay values with optional
    variance (jitter) and a hard maximum.

    Each call to `__next__` returns: base^steps * uniform(1±variance) + shift,
    capped at `maximum`.
    """
    def __init__(
        self,
        *,
        base: float = 2,
        variance: float | tuple[float, float] = 0.1,
        shift: float = 0,
        maximum: float = 300,
    ):
        if base <= 1:
            raise ValueError("Base has to be greater than 1")
        self.steps: int = 0
        self.base: float = float(base)
        self.shift: float = float(shift)
        self.maximum: float = float(maximum)
        self.variance_min: float
        self.variance_max: float
        if isinstance(variance, tuple):
            self.variance_min, self.variance_max = variance
        else:
            self.variance_min = 1 - variance
            self.variance_max = 1 + variance

    @property
    def exp(self) -> int:
        return max(0, self.steps - 1)

    def __iter__(self) -> abc.Iterator[float]:
        return self

    def __next__(self) -> float:
        value: float = (
            pow(self.base, self.steps)
            * random.uniform(self.variance_min, self.variance_max)
            + self.shift
        )
        if value > self.maximum:
            return self.maximum
        self.steps += 1
        return value

    def reset(self) -> None:
        self.steps = 0


# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------

class RateLimiter:
    """
    Async context manager that enforces at most `capacity` concurrent (and
    total per `window` seconds) usages of a resource.
    """
    def __init__(self, *, capacity: int, window: int):
        self.total: int = 0
        self.concurrent: int = 0
        self.window: int = window
        self.capacity: int = capacity
        self._reset_task: asyncio.Task[None] | None = None
        self._cond: asyncio.Condition = asyncio.Condition()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.concurrent}/{self.total}/{self.capacity})"

    def __del__(self) -> None:
        if self._reset_task is not None:
            self._reset_task.cancel()

    def _can_proceed(self) -> bool:
        return max(self.total, self.concurrent) < self.capacity

    async def __aenter__(self):
        async with self._cond:
            await self._cond.wait_for(self._can_proceed)
            self.total += 1
            self.concurrent += 1
            if self._reset_task is None:
                self._reset_task = asyncio.create_task(self._rtask())

    async def __aexit__(self, exc_type, exc, tb):
        self.concurrent -= 1
        async with self._cond:
            self._cond.notify(self.capacity - self.concurrent)

    async def _reset(self) -> None:
        if self._reset_task is not None:
            self._reset_task = None
        async with self._cond:
            self.total = 0
            if self.concurrent < self.capacity:
                self._cond.notify(self.capacity - self.concurrent)

    async def _rtask(self) -> None:
        await asyncio.sleep(self.window)
        await self._reset()


# ---------------------------------------------------------------------------
# AwaitableValue
# ---------------------------------------------------------------------------

class AwaitableValue(Generic[_T]):
    """A value that can be awaited until it is set."""

    def __init__(self):
        self._value: _T           # intentionally unassigned; guarded by _event
        self._event = asyncio.Event()

    def has_value(self) -> bool:
        return self._event.is_set()

    def wait(self) -> abc.Coroutine[Any, Any, Literal[True]]:
        return self._event.wait()

    def get_with_default(self, default: _D) -> _T | _D:
        if self._event.is_set():
            return self._value
        return default

    async def get(self) -> _T:
        await self._event.wait()
        return self._value

    def set(self, value: _T) -> None:
        self._value = value
        self._event.set()

    def clear(self) -> None:
        self._event.clear()


# ---------------------------------------------------------------------------
# Game
# ---------------------------------------------------------------------------

class Game:
    """Represents a Twitch game/category."""

    SPECIAL_EVENTS_GAME_ID: int = 509663

    def __init__(self, data: JsonType):
        self.id: int = int(data["id"])
        self.name: str = data.get("displayName") or data["name"]
        if "slug" in data:
            self.slug = data["slug"]

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"Game({self.id}, {self.name})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, self.__class__):
            return self.id == other.id
        return NotImplemented

    def __hash__(self) -> int:
        return self.id

    @cached_property
    def slug(self) -> str:
        """
        Derives the game slug from its display name for use with the GQL API.
        Only computed when not provided in the raw data.
        """
        slug_text = re.sub(r"'", '', self.name.lower())
        slug_text = re.sub(r'\W+', '-', slug_text)
        slug_text = re.sub(r'-{2,}', '-', slug_text.strip('-'))
        return slug_text

    def is_special_events(self) -> bool:
        return self.id == self.SPECIAL_EVENTS_GAME_ID


# ---------------------------------------------------------------------------
# Android-specific utilities
# ---------------------------------------------------------------------------

def is_network_available() -> bool:  # Android-specific
    """
    Return True if the Android device has an active network connection.

    Uses plyer's network_info facade when available; falls back to True on
    non-Android platforms (desktop testing) so the calling code is not blocked.
    """
    try:
        from plyer import network_info  # type: ignore[import]
        return network_info.is_connected()  # type: ignore[no-any-return]
    except (ImportError, NotImplementedError):
        return True  # assume connected on desktop / unsupported platform
