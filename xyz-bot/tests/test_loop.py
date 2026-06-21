"""Tests M4 : calcul du backoff + un cycle complet (run_cycle) sans réseau ni DB."""
import asyncio
import copy

from src.config import config
from src.main import api_alert_action, backoff_delay, run_cycle

from .fixtures import META_RESPONSE, PERP_DEX_LIMITS_RESPONSE


# --- backoff ---

def test_backoff_zero_error_is_poll_interval():
    assert backoff_delay(0) == config.poll_interval_sec


def test_backoff_grows_exponentially():
    assert backoff_delay(1) == config.poll_interval_sec * 2
    assert backoff_delay(2) == config.poll_interval_sec * 4


def test_backoff_is_capped():
    assert backoff_delay(50) == config.error_backoff_max_sec
    assert backoff_delay(1000) <= config.error_backoff_max_sec


# --- alerte API down/up ---

def test_api_alert_fires_down_once_at_threshold():
    assert api_alert_action(3, 3, alerted=False) == "down"   # seuil atteint → alerter
    assert api_alert_action(5, 3, alerted=True) is None        # déjà alerté → pas de spam


def test_api_alert_silent_below_threshold():
    assert api_alert_action(1, 3, alerted=False) is None
    assert api_alert_action(2, 3, alerted=False) is None


def test_api_alert_recovers_once():
    assert api_alert_action(0, 3, alerted=True) == "up"        # rétabli → notifier
    assert api_alert_action(0, 3, alerted=False) is None       # jamais tombé → rien


# --- run_cycle (duck-typed client + notifier, pas de DB → fallback mémoire) ---

class FakeClient:
    def __init__(self, meta, limits):
        self._meta, self._limits = meta, limits

    async def get_meta(self, dex):
        return self._meta

    async def get_perp_dex_limits(self, dex):
        return self._limits

    async def aclose(self):
        pass


class SpyNotifier:
    dry_run = True

    def __init__(self):
        self.sent = []

    async def send(self, text):
        self.sent.append(text)

    async def aclose(self):
        pass


def test_run_cycle_seeds_then_alerts():
    async def scenario():
        spy = SpyNotifier()

        # cycle 1 : pas de baseline → seed silencieux
        client1 = FakeClient(META_RESPONSE, PERP_DEX_LIMITS_RESPONSE)
        snap1 = await run_cycle(client1, None, spy, None)
        assert spy.sent == []
        assert len(snap1.coins) == len(META_RESPONSE["universe"])

        # cycle 2 : un OI cap change → une alerte envoyée
        limits2 = copy.deepcopy(PERP_DEX_LIMITS_RESPONSE)
        for pair in limits2["coinToOiCap"]:
            if pair[0] == "xyz:HOOD":
                pair[1] = "99000000.0"
        client2 = FakeClient(META_RESPONSE, limits2)
        await run_cycle(client2, None, spy, snap1)
        assert any("OI cap changed — xyz:HOOD" in m for m in spy.sent)

    asyncio.run(scenario())


def test_run_cycle_no_change_no_alert():
    async def scenario():
        spy = SpyNotifier()
        client = FakeClient(META_RESPONSE, PERP_DEX_LIMITS_RESPONSE)
        snap1 = await run_cycle(client, None, spy, None)         # seed
        await run_cycle(client, None, spy, snap1)                # identique
        assert spy.sent == []                                    # aucune alerte
    asyncio.run(scenario())
