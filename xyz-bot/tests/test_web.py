"""Tests M-status : assemblage du payload de statut + rendu HTML (purs, sans DB ni serveur)."""
from datetime import datetime, timedelta, timezone

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
    """Pas d'injection HTML via les valeurs d'event."""
    ev = _event(NOW, coin="<script>", new="<b>x</b>")
    html = render_html(status_payload(_status(NOW), [ev], NOW))
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
