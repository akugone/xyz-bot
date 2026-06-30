"""Status payload assembly, HTML rendering, and the read cache (no server)."""
import asyncio
from datetime import datetime, timedelta, timezone

import src.web as web
from src.web import render_html, status_payload

NOW = datetime(2026, 6, 21, 12, 0, 0, tzinfo=timezone.utc)


def _status(last_cycle_at, markets=93, errors=0, started=None):
    return {
        "dex": "xyz",
        "started_at": started or (NOW - timedelta(hours=2)),
        "last_cycle_at": last_cycle_at,
        "markets_count": markets,
        "consecutive_errors": errors,
    }


def _event(at, etype="oi_cap_change", coin="xyz:NVDA", old="5000000.0", new="10000000.0"):
    return {"created_at": at, "event_type": etype, "coin": coin, "old_value": old, "new_value": new}


def test_up_when_recent_cycle():
    p = status_payload(_status(NOW - timedelta(seconds=5)), [], NOW)
    assert p["up"] is True
    assert p["markets_count"] == 93
    assert p["last_cycle_age_sec"] == 5


def test_down_when_stale():
    p = status_payload(_status(NOW - timedelta(minutes=10)), [], NOW)
    assert p["up"] is False


def test_absolute_time_displays():
    p = status_payload(_status(NOW), [], NOW)
    assert p["last_cycle_at_display"].endswith("UTC")   # absolute, not "Ns ago"
    assert p["started_at_display"].endswith("UTC")


def test_render_shows_last_check_and_running_since():
    html = render_html(status_payload(_status(NOW), [], NOW))
    assert "Last check" in html
    assert "Running since" in html
    assert "UTC" in html


def test_header_links_rendered_only_when_set():
    # no links by default (URLs unset in payload)
    base = status_payload(_status(NOW), [], NOW)
    assert "class='links'" not in render_html(base)
    # links appear when the URLs are present
    base["telegram_url"] = "https://t.me/xyzalerts"
    base["uptime_url"] = "https://xyzbot.betteruptime.com/"
    html = render_html(base)
    assert "https://t.me/xyzalerts" in html
    assert "https://xyzbot.betteruptime.com/" in html
    assert "Telegram" in html and "Uptime" in html


def test_down_when_no_status():
    p = status_payload(None, [], NOW)
    assert p["up"] is False
    assert p["markets_count"] is None
    assert p["recent_events"] == []


def test_recent_events_mapped():
    p = status_payload(_status(NOW), [_event(NOW - timedelta(minutes=1))], NOW)
    assert len(p["recent_events"]) == 1
    ev = p["recent_events"][0]
    assert ev["type"] == "oi_cap_change"
    assert ev["coin"] == "xyz:NVDA"
    assert ev["new"] == "10000000.0"


def test_render_html_online():
    html = render_html(status_payload(_status(NOW), [_event(NOW)], NOW))
    assert "ONLINE" in html
    assert "xyz:NVDA" in html
    assert "<table" in html
    assert "/status.json" in html


def test_render_html_offline_and_empty():
    html = render_html(status_payload(None, [], NOW))
    assert "OFFLINE" in html
    assert "No alerts yet." in html


def test_render_html_escapes_values():
    """No HTML injection via event values."""
    ev = _event(NOW, coin="<script>", new="<b>x</b>")
    html = render_html(status_payload(_status(NOW), [ev], NOW))
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_render_html_formats_oi_cap_amounts():
    """OI-cap events render notionals with thousands separators (like Telegram)."""
    ev = _event(NOW, etype="oi_cap_change", old="1000000.0", new="50000000.0")
    html = render_html(status_payload(_status(NOW), [ev], NOW))
    assert "1,000,000 → 50,000,000" in html
    assert "1000000.0" not in html        # raw value not shown


def test_render_html_leaves_non_amount_events_raw():
    """Non-OI events (e.g. margin mode) are not number-formatted."""
    ev = _event(NOW, etype="margin_mode_change", old="noCross", new="normal")
    html = render_html(status_payload(_status(NOW), [ev], NOW))
    assert "noCross → normal" in html


# --- read cache (_read_cached / _build_payload) ---

class _FakeDB:
    def __init__(self, total=0):
        self.status_calls = 0
        self.events_calls = 0
        self.coins_calls = 0
        self.count_calls = 0
        self._total = total
        self.last_offset = None

    async def get_status(self, dex):
        self.status_calls += 1
        return _status(NOW)

    async def recent_events(self, dex, limit, offset=0):
        self.events_calls += 1
        self.last_offset = offset
        return []

    async def count_events(self, dex):
        self.count_calls += 1
        return self._total

    async def list_coins(self, dex):
        self.coins_calls += 1
        return ["xyz:HOOD", "xyz:NVDA"]


def _app(db):
    return {"db": db, "cache": {"at": 0.0, "base": None, "events": {}}}


def test_read_base_hits_db_once_within_ttl():
    db = _FakeDB()
    app = _app(db)

    async def scenario():
        await web._read_base(app)
        await web._read_base(app)   # within TTL → served from cache

    asyncio.run(scenario())
    assert db.status_calls == 1
    assert db.count_calls == 1


def test_read_base_refreshes_after_ttl():
    db = _FakeDB()
    app = _app(db)

    async def scenario():
        await web._read_base(app)
        app["cache"]["at"] = -10_000   # force staleness
        await web._read_base(app)

    asyncio.run(scenario())
    assert db.status_calls == 2


def test_build_payload_uses_db_rows():
    payload = asyncio.run(web._build_payload(_app(_FakeDB())))
    assert payload["markets_count"] == 93
    assert payload["recent_events"] == []
    assert payload["markets"] == ["xyz:HOOD", "xyz:NVDA"]


def test_build_payload_clamps_page_and_sets_offset():
    db = _FakeDB(total=45)  # 45 events, 20/page → 3 pages
    payload = asyncio.run(web._build_payload(_app(db), page=2))
    assert payload["pagination"]["page"] == 2
    assert payload["pagination"]["total_pages"] == 3
    assert db.last_offset == 20  # (page-1) * page_size
    # page beyond the end is clamped to the last page
    payload_hi = asyncio.run(web._build_payload(_app(_FakeDB(total=45)), page=99))
    assert payload_hi["pagination"]["page"] == 3


def test_render_html_lists_tokens_in_tooltip():
    payload = status_payload(_status(NOW), [], NOW, coins=["xyz:HOOD", "xyz:NVDA"])
    html = render_html(payload)
    assert "class='info'" in html or 'class="info"' in html   # info icon/tooltip present
    assert "HOOD" in html and "NVDA" in html                   # tokens listed
    assert "xyz:HOOD" not in html                              # dex prefix stripped


# --- pagination ---

def test_pagination_block_in_payload():
    p = status_payload(_status(NOW), [_event(NOW)], NOW, page=2, total=45)
    pg = p["pagination"]
    assert pg["page"] == 2
    assert pg["total"] == 45
    assert pg["total_pages"] == 3          # ceil(45 / 20)
    assert pg["has_prev"] is True
    assert pg["has_next"] is True


def test_parse_page_handles_bad_input():
    assert web._parse_page("3") == 3
    assert web._parse_page(None) == 1
    assert web._parse_page("abc") == 1
    assert web._parse_page("-5") == 1      # clamped to >= 1


def test_render_html_shows_pager_when_multiple_pages():
    html = render_html(status_payload(_status(NOW), [_event(NOW)], NOW, page=2, total=45))
    assert "class='pager'" in html
    assert "Page 2 / 3" in html
    assert "/?page=1" in html              # link to newer page
    assert "/?page=3" in html              # link to older page
    assert "(45 total)" in html


def test_render_html_no_pager_on_single_page():
    html = render_html(status_payload(_status(NOW), [_event(NOW)], NOW))
    assert "class='pager'" not in html
