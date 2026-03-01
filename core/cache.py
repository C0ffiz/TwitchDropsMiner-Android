# Android-specific: ImageCache is not yet wired into TwitchClient; reserved for future drop image display.
"""Image cache for TwitchDropsMiner Android.

Desktop counterpart (TwitchDropsMiner/cache.py) stores PIL images in
tkinter.PhotoImage objects and resolves paths from flat constants.
This Android port:
  - Returns local file paths (str) that Kivy Image/AsyncImage widgets can
    load via ``source=``.  Kivy handles display scaling; the cache no longer
    pre-scales images to a caller-supplied ``size``.
  - Defers all filesystem access until the first ``await get()`` call so
    that ``App.user_data_dir`` (Kivy) is guaranteed to be available.
  - Serialises the hash database with core.utils.json_save / json_load, which
    correctly round-trips datetime objects via the existing ``_serialize`` /
    ``_deserialize`` hooks.
  - Provides ``clear()`` and ``invalidate()`` helpers for logout / reset flows
    that are absent from the desktop version.

Porting rules applied:
  - No tkinter, no PhotoImage, no desktop path constants.
  - All imports use ``core.*`` paths.
  - Path resolution via ``get_app_paths()`` from core.constants (Android-specific).
"""
from __future__ import annotations

import asyncio
import io
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, NewType, Optional, TypedDict, TYPE_CHECKING

from PIL import Image as Image_module

from core.constants import URLType, get_app_paths
from core.utils import json_load, json_save

if TYPE_CHECKING:
    from core.twitch_client import TwitchClient
    from typing_extensions import TypeAlias
    from PIL.Image import Image


logger = logging.getLogger("TwitchDrops")

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

ImageHash = NewType("ImageHash", str)
# Android-specific: kept for API symmetry with desktop; Kivy scales in widget.
ImageSize: TypeAlias = "tuple[int, int]"


class ExpiringHash(TypedDict):
    hash: ImageHash
    expires: datetime


Hashes = Dict[URLType, ExpiringHash]
_default_database: Hashes = {}


# ---------------------------------------------------------------------------
# ImageCache
# ---------------------------------------------------------------------------

class ImageCache:
    """Disk-backed image cache.

    On Android the cache directory lives inside ``App.user_data_dir`` so
    path resolution *must* be deferred until after the Kivy App has started.
    Call ``await cache.get(url)`` from any coroutine running after
    ``App.on_start``; the first call initialises the cache lazily.
    """

    LIFETIME = timedelta(days=7)

    def __init__(self, twitch_client: TwitchClient) -> None:
        # Android-specific: takes TwitchClient instead of GUIManager so the
        # cache can reuse the existing aiohttp session for image downloads.
        self._twitch = twitch_client
        self._hashes: Hashes = {}
        self._images: dict[ImageHash, Image] = {}
        self._lock = asyncio.Lock()
        self._altered: bool = False
        # Android-specific: delayed init flag; the cache dir is not known yet.
        self._initialized: bool = False

    # ------------------------------------------------------------------
    # Lazy path properties                                  Android-specific
    # ------------------------------------------------------------------

    @property
    def _cache_dir(self) -> Path:  # Android-specific
        """Cache directory inside App.user_data_dir.  Resolved on first access."""
        return get_app_paths()["cache"]

    @property
    def _cache_db(self) -> Path:  # Android-specific
        """Path to the JSON file that maps image URLs to on-disk hashes."""
        return self._cache_dir / "hashes.json"

    # ------------------------------------------------------------------
    # Initialisation (deferred)
    # ------------------------------------------------------------------

    def _initialize(self) -> None:
        """Create the cache directory, load existing hashes, and evict expired entries.

        Intentionally synchronous — called once from within the async ``get()``
        while holding ``self._lock``, so it does not need to be a coroutine.
        """  # Android-specific: deferred so App.user_data_dir is available
        cleanup: bool = False
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._hashes = json_load(self._cache_db, _default_database, merge=False)
        except Exception:
            # Corrupt or unreadable database: start fresh and clean up files.
            cleanup = True
            self._hashes = _default_database.copy()

        # Evict expired entries and count remaining references per hash.
        hash_counts: dict[ImageHash, int] = {}
        now = datetime.now(timezone.utc)
        for url, hash_dict in list(self._hashes.items()):
            img_hash = hash_dict["hash"]
            if img_hash not in hash_counts:
                hash_counts[img_hash] = 0
            if now >= hash_dict["expires"]:
                del self._hashes[url]
                self._altered = True
            else:
                hash_counts[img_hash] += 1

        # Delete unreferenced image files.
        for img_hash, count in hash_counts.items():
            if count == 0:
                self._cache_dir.joinpath(img_hash).unlink(missing_ok=True)

        if cleanup:
            # Remove any PNG files that are not in the (now-rebuilt) hash map.
            orphans = [
                file.name
                for file in self._cache_dir.glob("*.png")
                if file.name not in hash_counts
            ]
            for filename in orphans:
                self._cache_dir.joinpath(filename).unlink(missing_ok=True)

        self._initialized = True

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, *, force: bool = False) -> None:
        """Flush the hash database to disk (synchronous)."""
        if (self._altered or force) and self._initialized:
            json_save(self._cache_db, self._hashes, sort=True)
            self._altered = False

    async def save_async(self, *, force: bool = False) -> None:  # Android-specific
        """Flush the hash database to disk without blocking the event loop.

        Runs ``save()`` in the default executor so that file I/O does not
        stall Kivy's main thread on slower Android devices.
        """
        if (self._altered or force) and self._initialized:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: self.save(force=force))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _new_expires(self) -> datetime:
        return datetime.now(timezone.utc) + self.LIFETIME

    def _hash(self, image: Image) -> ImageHash:
        """Compute a perceptual (average-hash) fingerprint for *image*.

        Returns a hex string with a '.png' suffix so it can be used directly
        as a filename.
        """
        pixel_data = list(
            image.resize((10, 10), Image_module.Resampling.LANCZOS).convert("L").getdata()
        )
        avg_pixel = sum(pixel_data) / len(pixel_data)
        bits = "".join("1" if px >= avg_pixel else "0" for px in pixel_data)
        return ImageHash(f"{int(bits, 2):x}.png")

    # ------------------------------------------------------------------
    # Main API
    # ------------------------------------------------------------------

    async def get(self, url: URLType, size: ImageSize | None = None) -> str:
        """Return a local file path for the image at *url*.

        Downloads and caches the image on first access.  Returns a path to a
        10×10 white placeholder PNG if the download fails.

        ``size`` is accepted for API symmetry with the desktop version but is
        not applied — Kivy Image widgets handle display scaling at the widget
        level.  Pass it if future code needs to pre-scale, but ignore it for
        now.
        """  # Android-specific: returns str path, not tkinter PhotoImage
        async with self._lock:
            if not self._initialized:
                self._initialize()

            image: Optional[Image] = None
            img_hash: ImageHash

            if url in self._hashes:
                img_hash = self._hashes[url]["hash"]
                # Refresh expiry on every access.
                self._hashes[url]["expires"] = self._new_expires()
                if img_hash in self._images:
                    image = self._images[img_hash]
                else:
                    try:
                        self._images[img_hash] = image = Image_module.open(
                            self._cache_dir / img_hash
                        )
                    except (FileNotFoundError, Image_module.UnidentifiedImageError):
                        pass

            if image is None:
                try:
                    # Android-specific: reuse TwitchClient's aiohttp session.
                    session = await self._twitch.get_session()
                    async with session.get(str(url)) as response:
                        if response.status != 404:
                            image = Image_module.open(
                                io.BytesIO(await response.read())
                            )
                except Exception:
                    logger.debug("Failed to fetch image %r", url, exc_info=True)

                if image is None:
                    # Fallback: small white placeholder (same as desktop).
                    image = Image_module.new("RGB", (10, 10), (255, 255, 255))

                img_hash = self._hash(image)
                self._images[img_hash] = image
                image.save(self._cache_dir / img_hash)
                self._hashes[url] = {
                    "hash": img_hash,
                    "expires": self._new_expires(),
                }

            self._altered = True

        return str(self._cache_dir / img_hash)

    # ------------------------------------------------------------------
    # Maintenance                                           Android-specific
    # ------------------------------------------------------------------

    def clear(self) -> None:  # Android-specific
        """Remove all cached images and reset the hash database.

        Call on logout or when the user requests a cache wipe from Settings.
        Safe to call from synchronous (Kivy UI thread) code as long as no
        coroutine is currently inside ``get()``.
        """
        if not self._initialized:
            return
        for hash_dict in self._hashes.values():
            self._cache_dir.joinpath(hash_dict["hash"]).unlink(missing_ok=True)
        self._hashes = {}
        self._images = {}
        self._altered = True
        self.save(force=True)
        logger.debug("Image cache cleared")

    def invalidate(self, url: URLType) -> None:  # Android-specific
        """Remove a single URL from the cache so it will be re-fetched.

        Useful when an upstream game thumbnail changes without a URL change.
        """
        if url not in self._hashes:
            return
        img_hash = self._hashes.pop(url)["hash"]
        # Only delete the file if no other URL still references the same hash.
        if not any(h["hash"] == img_hash for h in self._hashes.values()):
            self._cache_dir.joinpath(img_hash).unlink(missing_ok=True)
            self._images.pop(img_hash, None)
        self._altered = True
