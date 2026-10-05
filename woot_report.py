import os
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

import config
import woot_db
from classifier import is_excluded
from woot_classifier import load_excludes, load_stockup, matches_stockup


def _money(v):
    return f"${v:,.2f}" if v is not None else "?"


def _range(lo, hi):
    return _money(lo) if hi is None or hi == lo else f"{_money(lo)} - {_money(hi)}"


def generate_item_card(item: dict) -> str:
    pct = woot_db.discount(item)
    off = f"{pct * 100:.0f}% off" if pct else ""
    list_str = f"{_range(item.get('list_min'), item.get('list_max'))} {off}".strip() if item.get("list_min") else ""
    badge = f'<span class="badge">{escape(item["condition"])}</span>' if item.get("condition") else ""
    ends = ""
    if item.get("end_date"):
        try:
            dt = datetime.fromisoformat(item["end_date"].replace("Z", "+00:00"))
            ends = "Ends: " + dt.astimezone(ZoneInfo("America/Chicago")).strftime("%b %d, %I:%M %p CT")
        except ValueError:
            ends = item["end_date"]
    return f"""
    <div class="card">
      <a href="{escape(item.get("url") or "#")}" target="_blank" class="card-link">
        <div class="card-img"><img src="{escape(item.get("photo_url") or "")}" alt="" loading="lazy" onerror="this.style.display='none'"></div>
        <div class="card-body">
          <div class="card-title">{escape(item["title"])}</div>
          <div class="card-prices">
            <span class="price-current">{_range(item.get("sale_min"), item.get("sale_max"))}</span>
            <span class="price-retail">{list_str}</span>
          </div>
          <div class="card-meta">{badge} <span class="ends">{escape(item.get("site") or "")}</span> <span class="ends">{ends}</span></div>
        </div>
      </a>
    </div>"""


def select_sections(offers: list[dict], excludes: list[str], stockup_terms: list[str]) -> dict[str, list[dict]]:
    """Split unnotified offers into interesting / stock-up / crazy deals (each offer lands in at most one)."""
    offers = [o for o in offers if not is_excluded(o["title"], excludes)]
    interesting = sorted((o for o in offers if o.get("interest_match")), key=lambda o: o["interest_match"])
    rest = [o for o in offers if not o.get("interest_match")]
    stockup = sorted(
        (o for o in rest if woot_db.discount(o) >= config.WOOT_STOCKUP_MIN_DISCOUNT and matches_stockup(o, stockup_terms)),
        key=woot_db.discount, reverse=True,
    )
    stock_ids = {o["offer_id"] for o in stockup}
    crazy = sorted(
        (o for o in rest if o["offer_id"] not in stock_ids
         and (o.get("list_min") or 0) >= config.WOOT_CRAZY_MIN_LIST
         and woot_db.discount(o) >= config.WOOT_CRAZY_MIN_DISCOUNT),
        key=woot_db.savings, reverse=True,
    )[:config.WOOT_CRAZY_MAX_ITEMS]
    return {"interesting": interesting, "stockup": stockup, "crazy": crazy}


CSS = """
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; padding: 20px; }
  .header { text-align: center; margin-bottom: 30px; }
  .header h1 { font-size: 1.8em; color: #fb923c; }
  .header .subtitle { color: #94a3b8; margin-top: 5px; }
  .section { margin-bottom: 40px; }
  .section h2 { font-size: 1.4em; color: #f8fafc; margin-bottom: 15px; border-bottom: 2px solid #334155; padding-bottom: 8px; }
  .section .count { color: #64748b; font-weight: normal; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }
  .card { background: #1e293b; border-radius: 12px; overflow: hidden; transition: transform 0.2s; }
  .card:hover { transform: translateY(-2px); }
  .card-link { text-decoration: none; color: inherit; display: block; }
  .card-img { height: 180px; background: #0f172a; display: flex; align-items: center; justify-content: center; overflow: hidden; }
  .card-img img { max-height: 100%; max-width: 100%; object-fit: contain; }
  .card-body { padding: 12px 16px; }
  .card-title { font-size: 0.9em; line-height: 1.3; height: 2.6em; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
  .card-prices { margin: 8px 0; }
  .price-current { font-size: 1.3em; font-weight: bold; color: #22c55e; }
  .price-retail { color: #64748b; margin-left: 8px; font-size: 0.9em; }
  .card-meta { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; font-size: 0.8em; }
  .badge { padding: 2px 8px; border-radius: 4px; color: #fff; background: #eab308; font-weight: 600; }
  .ends { color: #94a3b8; }
"""


def generate_report() -> str | None:
    sections = select_sections(woot_db.get_unnotified(), load_excludes(), load_stockup())
    shown = [o for lst in sections.values() for o in lst]
    if not shown:
        print("[woot-report] Nothing new to report.")
        return None

    titles = {
        "interesting": ("Interesting", "#38bdf8"),
        "stockup": ("Stock-Up Deals", "#a3e635"),
        "crazy": ("Crazy Deals", "#f472b6"),
    }
    body = ""
    for key, (name, color) in titles.items():
        if sections[key]:
            cards = "\n".join(generate_item_card(o) for o in sections[key])
            body += f"""
        <div class="section">
          <h2 style="color:{color}">{name} <span class="count">({len(sections[key])})</span></h2>
          <div class="grid">{cards}</div>
        </div>"""

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Woot Finds - {date_str}</title><style>{CSS}</style></head>
<body>
  <div class="header"><h1>Woot Finds</h1><div class="subtitle">{now.strftime("%B %d, %Y %I:%M %p")} - {len(shown)} new</div></div>
  {body}
</body></html>"""

    os.makedirs(config.REPORTS_DIR, exist_ok=True)
    path = os.path.join(config.REPORTS_DIR, f"woot-{date_str}.html")
    with open(path, "w") as f:
        f.write(html)
    woot_db.mark_notified([o["offer_id"] for o in shown])
    print(f"[woot-report] Report saved to {path}")
    return path


if __name__ == "__main__":
    generate_report()
