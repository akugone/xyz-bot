"""Backoff computation + a full cycle (run_cycle), no network and no DB."""
import asyncio
import copy
from types import SimpleNamespace

import src.main as main_mod
from src.config import config
from src.main import _ops_alert, api_alert_action, backoff_delay, run_cycle

from .fixtures import META_RESPONSE, PERP_DEX_LIMITS_RESPONSE, PERP_DEXS_RESPONSE


# --- backoff ---

def test_backoff_zero_error_is_poll_interval():
    assert backoff_delay(0) == config.poll_interval_sec


def test_backoff_grows_exponentially():
    assert backoff_delay(1) == config.poll_interval_sec * 2
    assert backoff_delay(2) == config.poll_interval_sec * 4


def test_backoff_is_capped():
    assert backoff_delay(50) == config.error_backoff_max_sec
    assert backoff_delay(1000) <= config.error_backoff_max_sec


# --- API down/up alert ---

def test_api_alert_fires_down_once_at_threshold():
    assert api_alert_action(3, 3, alerted=False) == "down"   # threshold reached → alert
    assert api_alert_action(5, 3, alerted=True) is None        # already alerted → no spam


def test_api_alert_silent_below_threshold():
    assert api_alert_action(1, 3, alerted=False) is None
    assert api_alert_action(2, 3, alerted=False) is None


def test_api_alert_recovers_once():
    assert api_alert_action(0, 3, alerted=True) == "up"        # recovered → notify
    assert api_alert_action(0, 3, alerted=False) is None       # never went down → nothing


# --- run_cycle (duck-typed client + notifier, no DB → memory fallback) ---

class FakeClient:
    def __init__(self, meta, limits, perp_dexs=None):
        self._meta, self._limits = meta, limits
        self._perp_dexs = perp_dexs if perp_dexs is not None else PERP_DEXS_RESPONSE

    async def get_meta(self, dex):
        return self._meta

    async def get_perp_dex_limits(self, dex):
        return self._limits

    async def get_perp_dexs(self):
        return self._perp_dexs

    async def aclose(self):
        pass


class SpyNotifier:
    dry_run = True

    def __init__(self):
        self.sent = []  # list of (text, chat_id)

    async def send(self, text, chat_id=None):
        self.sent.append((text, chat_id))

    async def send_photo(self, photo, caption, chat_id=None):
        # alerts go out as a photo card; the caption carries the text we assert on
        self.sent.append((caption, chat_id))

    async def aclose(self):
        pass


class _CountingNotifier:
    """Tracks text sends vs photo sends separately; can be told to fail on send_photo."""
    dry_run = True

    def __init__(self, photo_raises=False):
        self.texts = []
        self.photos = []
        self._photo_raises = photo_raises

    async def send(self, text, chat_id=None):
        self.texts.append(text)

    async def send_photo(self, photo, caption, chat_id=None):
        if self._photo_raises:
            raise RuntimeError("simulated send timeout")
        self.photos.append(caption)

    async def aclose(self):
        pass


def _trigger_one_oi_change(notifier):
    """Seed, then run a cycle where one market's OI cap changes (one event)."""
    async def scenario():
        snap1 = await run_cycle(FakeClient(META_RESPONSE, PERP_DEX_LIMITS_RESPONSE), None, notifier, None)
        limits2 = copy.deepcopy(PERP_DEX_LIMITS_RESPONSE)
        for pair in limits2["coinToOiCap"]:
            if pair[0] == "xyz:HOOD":
                pair[1] = "99000000.0"
        await run_cycle(FakeClient(META_RESPONSE, limits2), None, notifier, snap1)
    asyncio.run(scenario())


def test_send_photo_failure_does_not_fall_back_to_text():
    """A send_photo failure (e.g. ReadTimeout on a slow-but-delivered photo) must NOT send a
    text fallback — that duplicates the alert (card + text)."""
    n = _CountingNotifier(photo_raises=True)
    _trigger_one_oi_change(n)
    assert n.texts == []   # no text fallback → no duplicate


def test_render_failure_falls_back_to_text(monkeypatch):
    """If the card can't be rendered, we DO fall back to text (never drop the alert)."""
    monkeypatch.setattr(main_mod, "render_card", lambda ev: (_ for _ in ()).throw(RuntimeError("render boom")))
    n = _CountingNotifier()
    _trigger_one_oi_change(n)
    assert any("OI cap changed" in t for t in n.texts)   # fell back to text
    assert n.photos == []                                # no photo sent (render failed)


def test_run_cycle_seeds_then_alerts():
    async def scenario():
        spy = SpyNotifier()

        # cycle 1: no baseline → silent seed
        client1 = FakeClient(META_RESPONSE, PERP_DEX_LIMITS_RESPONSE)
        snap1 = await run_cycle(client1, None, spy, None)
        assert spy.sent == []
        assert len(snap1.coins) == len(META_RESPONSE["universe"])

        # cycle 2: one OI cap changes → one alert sent
        limits2 = copy.deepcopy(PERP_DEX_LIMITS_RESPONSE)
        for pair in limits2["coinToOiCap"]:
            if pair[0] == "xyz:HOOD":
                pair[1] = "99000000.0"
        client2 = FakeClient(META_RESPONSE, limits2)
        await run_cycle(client2, None, spy, snap1)
        assert any("OI cap changed · xyz:HOOD" in text for text, _ in spy.sent)

    asyncio.run(scenario())


def test_run_cycle_no_change_no_alert():
    async def scenario():
        spy = SpyNotifier()
        client = FakeClient(META_RESPONSE, PERP_DEX_LIMITS_RESPONSE)
        snap1 = await run_cycle(client, None, spy, None)         # seed
        await run_cycle(client, None, spy, snap1)                # identical
        assert spy.sent == []                                    # no alert
    asyncio.run(scenario())


# --- ops alert routing (_ops_alert) ---

def test_ops_alert_goes_to_admin_chat(monkeypatch):
    monkeypatch.setattr(main_mod, "config", SimpleNamespace(telegram_admin_chat_id="999"))
    spy = SpyNotifier()
    asyncio.run(_ops_alert(spy, "API down"))
    assert spy.sent == [("API down", "999")]   # sent to the admin chat


def test_ops_alert_without_admin_only_logs(monkeypatch):
    monkeypatch.setattr(main_mod, "config", SimpleNamespace(telegram_admin_chat_id=None))
    spy = SpyNotifier()
    asyncio.run(_ops_alert(spy, "API down"))
    assert spy.sent == []                       # no admin chat → logged only, nothing sent
