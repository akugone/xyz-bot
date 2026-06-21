"""Public status page (separate web service, read-only access to Postgres).

Decoupled from the daemon: runs in its own process / systemd service. Serves:
  - `GET /`            → HTML page (status + latest alerts), auto-refresh
  - `GET /status.json` → same info as JSON (machine-readable / monitoring)

`status_payload` and `render_html` are **pure** (no DB/HTTP) → testable.
"""
from __future__ import annotations

import html
import time
from datetime import datetime, timezone

from aiohttp import web

from .config import config
from .db import Database
from .events import OI_CAP_CHANGE, TOTAL_OI_CAP_CHANGE
from .util import format_amount

# Event types whose old/new values are notionals → render with thousands separators.
_AMOUNT_EVENTS = {OI_CAP_CHANGE, TOTAL_OI_CAP_CHANGE}

# Short cache of DB reads: amortizes queries if the public page is hit frequently
# (the last-cycle age is still recomputed on each request, so it stays fresh).
_CACHE_TTL_SEC = 3.0


# Beyond this delay without a cycle, the bot is considered "down" (heartbeat freshness).
def _stale_after() -> float:
    return max(60.0, config.poll_interval_sec * 3)


def status_payload(status, events, now: datetime, coins=()) -> dict:
    """Assemble the status dict from a `bot_status` row, recent events, and the coin list."""
    last = status["last_cycle_at"] if status else None
    age = (now - last).total_seconds() if last else None
    return {
        "dex": config.dex_name,
        "up": bool(last) and age is not None and age < _stale_after(),
        "markets_count": status["markets_count"] if status else None,
        "markets": list(coins),
        "consecutive_errors": status["consecutive_errors"] if status else None,
        "started_at": _iso(status["started_at"]) if status else None,
        "last_cycle_at": _iso(last),
        "last_cycle_age_sec": int(age) if age is not None else None,
        "recent_events": [
            {
                "at": _iso(e["created_at"]),
                "type": e["event_type"],
                "coin": e["coin"],
                "old": e["old_value"],
                "new": e["new_value"],
            }
            for e in events
        ],
    }


def render_html(payload: dict) -> str:
    up = payload["up"]
    dot = "🟢" if up else "🔴"
    state = "ONLINE" if up else "OFFLINE"
    color = "#16a34a" if up else "#dc2626"

    rows = "".join(
        f"<tr><td class='t'>{html.escape(e['at'] or '')}</td>"
        f"<td><span class='tag'>{html.escape(e['type'] or '')}</span></td>"
        f"<td>{html.escape(e['coin'] or '—')}</td>"
        f"<td>{_change_cell(e)}</td></tr>"
        for e in payload["recent_events"]
    ) or "<tr><td colspan='4' class='muted'>No alerts yet.</td></tr>"

    age = payload["last_cycle_age_sec"]
    age_txt = f"{age}s ago" if age is not None else "—"

    markets = payload.get("markets") or []
    count_txt = payload["markets_count"] if payload["markets_count"] is not None else "—"
    # display without the "xyz:" prefix; tooltip lists all tracked tokens
    tokens = ", ".join(html.escape(m.split(":")[-1]) for m in markets) or "—"
    markets_card = (
        f"<div class='k'>Markets watched <span class='info'>&#9432;"
        f"<span class='tip'>{tokens}</span></span></div>"
        f"<div class='v'>{count_txt}</div>"
    )

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="30">
<title>xyz deployer bot — status</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ font-family: -apple-system, system-ui, sans-serif; background:#0b0e14; color:#e6e6e6;
         margin:0; padding:2rem 1rem; }}
  .wrap {{ max-width: 760px; margin: 0 auto; }}
  h1 {{ font-size: 1.25rem; margin:0 0 1.5rem; }}
  .badge {{ font-weight:700; color:{color}; }}
  .grid {{ display:grid; grid-template-columns: repeat(auto-fit,minmax(150px,1fr)); gap:1rem; margin-bottom:2rem; }}
  .card {{ background:#141925; border:1px solid #232a3a; border-radius:10px; padding:1rem; }}
  .card .k {{ font-size:.7rem; text-transform:uppercase; letter-spacing:.05em; color:#8a93a6; }}
  .card .v {{ font-size:1.2rem; margin-top:.25rem; }}
  table {{ width:100%; border-collapse:collapse; font-size:.85rem; }}
  th,td {{ text-align:left; padding:.5rem .6rem; border-bottom:1px solid #232a3a; }}
  th {{ color:#8a93a6; font-weight:600; font-size:.7rem; text-transform:uppercase; }}
  td.t {{ color:#8a93a6; white-space:nowrap; }}
  .tag {{ background:#1f2a44; color:#9db4ff; border-radius:5px; padding:.1rem .4rem; font-size:.75rem; }}
  .muted {{ color:#8a93a6; text-align:center; }}
  a {{ color:#9db4ff; }}
  .info {{ position:relative; cursor:help; color:#8a93a6; margin-left:.25rem; }}
  .info .tip {{ display:none; position:absolute; left:0; top:1.5em; z-index:10;
    width:380px; max-width:85vw; max-height:70vh; overflow-y:auto;
    background:#0b0e14; border:1px solid #2b3650; border-radius:8px; padding:.7rem .8rem;
    font-size:.75rem; line-height:1.7; color:#cbd5e1; font-weight:400;
    box-shadow:0 8px 28px rgba(0,0,0,.6); }}
  .info:hover .tip {{ display:block; }}
  footer {{ margin-top:2rem; color:#8a93a6; font-size:.8rem; }}
</style></head>
<body><div class="wrap">
  <h1>{dot} xyz deployer alerts — <span class="badge">{state}</span></h1>
  <div class="grid">
    <div class="card"><div class="k">Dex</div><div class="v">{html.escape(payload['dex'] or '—')}</div></div>
    <div class="card">{markets_card}</div>
    <div class="card"><div class="k">Last check</div><div class="v">{age_txt}</div></div>
    <div class="card"><div class="k">Errors (streak)</div><div class="v">{payload['consecutive_errors'] if payload['consecutive_errors'] is not None else '—'}</div></div>
  </div>
  <h2 style="font-size:1rem;">Latest alerts</h2>
  <table><thead><tr><th>Time (UTC)</th><th>Type</th><th>Market</th><th>Change</th></tr></thead>
  <tbody>{rows}</tbody></table>
  <footer>Live config changes on the <b>{html.escape(payload['dex'] or '')}</b> dex (Hyperliquid HIP-3).
  Auto-refresh 30s · <a href="/status.json">JSON</a></footer>
</div></body></html>"""


def _change_cell(e: dict) -> str:
    """Render the "old → new" cell, formatting notionals for OI-cap events."""
    fmt = format_amount if e["type"] in _AMOUNT_EVENTS else str
    old = fmt(e["old"]) if e["old"] is not None else "—"
    new = fmt(e["new"]) if e["new"] is not None else "—"
    return f"{html.escape(old)} → {html.escape(new)}"


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


# --- app aiohttp ---

async def _handle_index(request: web.Request) -> web.Response:
    payload = await _build_payload(request.app)
    return web.Response(text=render_html(payload), content_type="text/html")


async def _handle_json(request: web.Request) -> web.Response:
    return web.json_response(await _build_payload(request.app))


async def _build_payload(app: web.Application) -> dict:
    status, events, coins = await _read_cached(app)
    return status_payload(status, events, datetime.now(timezone.utc), coins)


async def _read_cached(app: web.Application):
    """Read (status, events, coins) from the DB, with a TTL cache to limit load."""
    cache = app["cache"]
    now = time.monotonic()
    if cache["rows"] is None or now - cache["at"] > _CACHE_TTL_SEC:
        db: Database = app["db"]
        cache["rows"] = (
            await db.get_status(config.dex_name),
            await db.recent_events(config.dex_name, 20),
            await db.list_coins(config.dex_name),
        )
        cache["at"] = now
    return cache["rows"]


async def _on_startup(app: web.Application) -> None:
    # Dedicated read-only role if provided (least privilege); otherwise the main DSN.
    db = Database(config.web_pg_dsn or config.pg_dsn)
    await db.connect()
    app["db"] = db
    app["cache"] = {"at": 0.0, "rows": None}


async def _on_cleanup(app: web.Application) -> None:
    await app["db"].close()


def make_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", _handle_index)
    app.router.add_get("/status.json", _handle_json)
    app.on_startup.append(_on_startup)
    app.on_cleanup.append(_on_cleanup)
    return app


def main() -> None:
    if not (config.web_pg_dsn or config.pg_dsn):
        raise SystemExit("PG_DSN (or WEB_PG_DSN) is required for the status page")
    web.run_app(make_app(), host=config.web_host, port=config.web_port)


if __name__ == "__main__":
    main()
