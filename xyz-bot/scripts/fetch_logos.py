#!/usr/bin/env python3
"""Build the static logo pack under `assets/logos/{SYMBOL}.png` — run once / occasionally.

Strategy (deliberately conservative):
  - Fetch the live `xyz` universe from the Hyperliquid info API.
  - Only attempt a logo for tickers classified as `other` by `cards.category_of`
    (i.e. equities / ETFs / brand-name tokens). Metals, energy, forex, indices and
    agri are SKIPPED on purpose: a stock-logo API has no entry for them, or worse maps
    an ambiguous ticker to the wrong company (GOLD → Barrick, CL → Colgate). Those use
    the colored category tile instead.
  - Validate each download is a real image (PIL-openable, >= 48px) before keeping it.

Logos come from Financial Modeling Prep's public image endpoint. Not every equity is
covered (404s are normal); uncovered tickers fall back to a tile too. Re-run after new
listings to pick up freshly available logos.

Usage:  python -m scripts.fetch_logos          (from the xyz-bot/ dir, venv active)
"""
from __future__ import annotations

import io
import json
import sys
import urllib.request
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.cards import category_of, symbol_of  # noqa: E402

HL_API = "https://api.hyperliquid.xyz/info"
DEX = "xyz"
FMP = "https://financialmodelingprep.com/image-stock/{sym}.png"
LOGOS_DIR = Path(__file__).resolve().parent.parent / "assets" / "logos"
MIN_PX = 48


def _post(payload: dict) -> dict:
    req = urllib.request.Request(
        HL_API, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def _fetch(url: str) -> bytes | None:
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            if r.status != 200:
                return None
            return r.read()
    except Exception:
        return None


def _valid_logo(data: bytes | None) -> Image.Image | None:
    if not data or len(data) < 800:  # 404 bodies are tiny
        return None
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception:
        return None
    if min(im.size) < MIN_PX:
        return None
    return im


def main() -> int:
    LOGOS_DIR.mkdir(parents=True, exist_ok=True)
    meta = _post({"type": "meta", "dex": DEX})
    universe = [a["name"] for a in meta.get("universe", [])]

    kept, skipped, missing = [], [], []
    for name in universe:
        sym = symbol_of(name)
        if category_of(sym) != "other":
            skipped.append(sym)  # metal/energy/forex/index/agri → category tile
            continue
        im = _valid_logo(_fetch(FMP.format(sym=sym)))
        if im is None:
            missing.append(sym)
            continue
        im.convert("RGBA").save(LOGOS_DIR / f"{sym}.png")
        kept.append(sym)

    print(f"universe: {len(universe)} markets")
    print(f"✅ logos saved ({len(kept)}): {', '.join(sorted(kept))}")
    print(f"⏭️  category-tile (skipped {len(skipped)}): {', '.join(sorted(skipped))}")
    print(f"❓ no logo found ({len(missing)}): {', '.join(sorted(missing))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
