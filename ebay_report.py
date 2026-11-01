import os
from collections import defaultdict
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

import config
import ebay_db
from classifier import is_excluded
from woot_report import CSS as WOOT_CSS

COLORS = ["#f472b6", "#38bdf8", "#a3e635", "#fbbf24", "#c084fc"]


def load_excludes() -> list[str]:
    if not os.path.exists(config.EBAY_EXCLUDE_FILE):
        return []
    with open(config.EBAY_EXCLUDE_FILE) as f:
        return [l.strip().lower() for l in f if l.strip() and not l.startswith("#")]


def _money(v):
    return f"${v:,.2f}" if v is not None else "?"


def generate_item_card(item: dict) -> str:
    ship = "free ship" if item.get("shipping") == 0 else (f"+{_money(item['shipping'])} ship" if item.get("shipping") else "ship ?")
    bids = item.get("bid_count") or 0
    ends = ""
    if item.get("end_date"):
        try:
            dt = datetime.fromisoformat(item["end_date"].replace("Z", "+00:00"))
            ends = "Ends: " + dt.astimezone(ZoneInfo("America/Chicago")).strftime("%a %b %d, %I:%M %p CT")
        except ValueError:
            ends = item["end_date"]
    badge = f'<span class="badge">{escape(item["condition"])}</span>' if item.get("condition") else ""
    return f"""
    <div class="card">
      <a href="{escape(item.get("url") or "#")}" target="_blank" class="card-link">
        <div class="card-img"><img src="{escape(item.get("photo_url") or "")}" alt="" loading="lazy" onerror="this.style.display='none'"></div>
        <div class="card-body">
          <div class="card-title">{escape(item["title"])}</div>
          <div class="card-prices">
            <span class="price-current">{_money(item.get("current_bid"))}</span>
            <span class="price-retail">{bids} bid{'s' if bids != 1 else ''} · {ship}</span>
          </div>
          <div class="card-meta">{badge} <span class="ends">{ends}</span></div>
        </div>
      </a>
    </div>"""


def select_sections(items: list[dict], excludes: list[str]) -> dict[str, list[dict]]:
    """Group unnotified items by watchlist term (file order), soonest-ending first."""
    groups = defaultdict(list)
    for i in items:
        if not is_excluded(i["title"], excludes):
            groups[i["query"]].append(i)
    return {q: sorted(lst, key=lambda i: i["end_date"] or "") for q, lst in groups.items()}


def generate_report() -> str | None:
    sections = select_sections(ebay_db.get_unnotified(), load_excludes())
    shown = [i for lst in sections.values() for i in lst]
    if not shown:
        print("[ebay-report] Nothing new to report.")
        return None

    body = ""
    for n, (term, lst) in enumerate(sorted(sections.items(), key=lambda kv: len(kv[1]))):  # rare terms first
        cards = "\n".join(generate_item_card(i) for i in lst)
        body += f"""
        <div class="section">
          <h2 style="color:{COLORS[n % len(COLORS)]}">{escape(term)} <span class="count">({len(lst)})</span></h2>
          <div class="grid">{cards}</div>
        </div>"""

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>eBay Watchlist - {date_str}</title><style>{WOOT_CSS}</style></head>
<body>
  <div class="header"><h1>eBay Watchlist</h1><div class="subtitle">{now.strftime("%B %d, %Y %I:%M %p")} - {len(shown)} new</div></div>
  {body}
</body></html>"""

    os.makedirs(config.REPORTS_DIR, exist_ok=True)
    path = os.path.join(config.REPORTS_DIR, f"ebay-{date_str}.html")
    with open(path, "w") as f:
        f.write(html)
    ebay_db.mark_notified([i["item_id"] for i in shown])
    print(f"[ebay-report] Report saved to {path}")
    return path


if __name__ == "__main__":
    generate_report()
