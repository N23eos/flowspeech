"""Runtime configuration: one owner for the current AppConfig.

AppConfig itself stays immutable (that is a feature: no code can mutate
settings behind anyone's back). When something changes at runtime — the user
saves API keys in the settings window, toggles private mode, edits
config.yaml — the manager rebuilds a fresh AppConfig and hands it to every
subscriber. Subscribers use it to drop cached API clients so new keys and
endpoints apply without a restart.

Deliberately not an event bus: one config object, one change callback shape,
synchronous notification. (SPEC.md §7.)
"""

import logging
import threading
from collections.abc import Callable

from flowspeech import secrets
from flowspeech.config import AppConfig, ConfigError, load_config

logger = logging.getLogger(__name__)

Subscriber = Callable[[AppConfig], None]


class ConfigManager:
    def __init__(self, config: AppConfig):
        self._lock = threading.RLock()
        self._config = config
        self._subscribers: list[Subscriber] = []

    @property
    def config(self) -> AppConfig:
        with self._lock:
            return self._config

    def subscribe(self, fn: Subscriber) -> None:
        """`fn` is called with the new AppConfig after every change.

        Called synchronously on whatever thread triggered the change; UI
        subscribers must hop to the main thread themselves.
        """
        with self._lock:
            self._subscribers.append(fn)

    def reload(self) -> AppConfig:
        """Re-read config.yaml and .env; on any error keep the old config.

        A broken edit of config.yaml must never take down a running app —
        the previous, known-good config stays active and the error is
        reported to the caller via the log (and re-raised for UI contexts
        that want to show it).
        """
        try:
            new_config = load_config()
        except ConfigError:
            logger.exception("Config reload failed; keeping the previous config")
            raise
        self._swap(new_config)
        return new_config

    def apply_keys(self, updates: dict[str, str | None]) -> AppConfig:
        """Persist API keys to ~/.flowspeech/.env and apply them immediately.

        Values are written with 0600 permissions, pushed into os.environ,
        and a rebuilt AppConfig (with fresh ProviderConfig.api_key values)
        is delivered to subscribers. Never logs the values themselves.
        """
        with self._lock:
            data_dir = self._config.data_dir
        secrets.save_keys(data_dir, updates)
        secrets.apply_to_environ(updates)
        logger.info("API keys updated: %s", ", ".join(sorted(updates)))
        return self.reload()

    def _swap(self, new_config: AppConfig) -> None:
        with self._lock:
            self._config = new_config
            subscribers = list(self._subscribers)
        for fn in subscribers:
            try:
                fn(new_config)
            except Exception:
                # One broken subscriber must not starve the others.
                logger.exception("Config subscriber failed")
