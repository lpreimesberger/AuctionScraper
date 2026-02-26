import os
from datetime import datetime
from itertools import groupby

import config
import db


def generate_item_card(item: dict) -> str:
    product_url = config.product_url(item["id"], item.get("title", ""))
    photo = item.get("photo_url") or ""
    title = item.get("title", "Unknown")
    retail = item.get("retail_price")
    current = item.get("current_price")
    bids = item.get("bid_count", 0)
    cond = item.get("condition", "?")
    functional = item.get("functional", "?")
    damage = item.get("damage", "?")
    rating = item.get("rating", "?")
    close = item.get("close_time", "")

    # Format close time
    close_display = ""
    if close:
        try:
            dt = datetime.fromisoformat(close.replace("Z", "+00:00"))
            close_display = dt.strftime("%b %d, %I:%M %p CT")
        except ValueError:
            close_display = close

    # Price display
    retail_str = f"${retail:.2f}" if retail else "?"
    current_str = f"${current:.2f}" if current is not None else "$1"
    savings = ""
    if retail and current is not None and retail > 0:
        pct = ((retail - current) / retail) * 100
        savings = f"({pct:.0f}% off)"

    # Condition badges
    badges = []
    if cond:
        color = "#22c55e" if cond == "New" else "#eab308"
        badges.append(f'<span class="badge" style="background:{color}">{cond}</span>')
    if functional and functional != "Yes":
        badges.append(
            f'<span class="badge" style="background:#ef4444">{functional}</span>'
        )
    if damage and damage != "None":
        badges.append(
            f'<span class="badge" style="background:#f97316">{damage} damage</span>'
        )

    return f"""
    <div class="card">
      <a href="{product_url}" target="_blank" class="card-link">
        <div class="card-img">
          <img src="{photo}" alt="" loading="lazy" onerror="this.style.display='none'">
        </div>
        <div class="card-body">
          <div class="card-title">{title}</div>
          <div class="card-prices">
            <span class="price-current">{current_str}</span>
            <span class="price-retail">{retail_str} {savings}</span>
          </div>
          <div class="card-meta">
            {" ".join(badges)}
            <span class="bids">{bids} bid{"s" if bids != 1 else ""}</span>
            <span class="closes">Ends: {close_display}</span>
          </div>
        </div>
      </a>
    </div>"""


def load_excludes() -> list[str]:
    if not os.path.exists(config.EXCLUDE_FILE):
        return []
    with open(config.EXCLUDE_FILE) as f:
        return [line.strip().lower() for line in f if line.strip()]


def is_excluded(title: str, excludes: list[str]) -> bool:
    title_lower = title.lower()
    return any(term in title_lower for term in excludes)


def generate_report() -> str | None:
    """Generate an HTML report of interesting items. Returns path to report file, or None."""
    items = db.get_report_items()
    
    # Fetch crazy deals
    crazy_items = db.get_crazy_deals(
        min_retail=config.CRAZY_DEAL_MIN_RETAIL,
        max_ratio=config.CRAZY_DEAL_MAX_RATIO
    )
    
    # Filter excludes from crazy items
    excludes = load_excludes()
    crazy_items = [i for i in crazy_items if not is_excluded(i.get("title", ""), excludes)]

    if not items and not crazy_items:
        print("[report] No new interesting items or crazy deals to report.")
        return None

    print(f"[report] Generating report for {len(items)} interesting items and {len(crazy_items)} crazy deals...")

    os.makedirs(config.REPORTS_DIR, exist_ok=True)

    # Group by interest match
    items.sort(key=lambda x: x.get("interest_match", ""))
    groups = {}
    for key, group in groupby(items, key=lambda x: x.get("interest_match", "other")):
        groups[key] = list(group)

    # Build sections
    sections_html = ""
    for interest, group_items in sorted(groups.items()):
        cards = "\n".join(generate_item_card(item) for item in group_items)
        sections_html += f"""
        <div class="section">
          <h2>{interest.title()} <span class="count">({len(group_items)})</span></h2>
          <div class="grid">{cards}</div>
        </div>"""

    # Add Crazy Deals section
    if crazy_items:
        cards = "\n".join(generate_item_card(item) for item in crazy_items)
        sections_html += f"""
        <div class="section">
          <h2 style="color: #f472b6; border-color: #be185d;">Crazy Deals <span class="count">({len(crazy_items)})</span></h2>
          <div class="grid">{cards}</div>
        </div>"""

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    stats = db.get_stats()

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nellis Auction Finds - {date_str}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #0f172a; color: #e2e8f0; padding: 20px; }}
  .header {{ text-align: center; margin-bottom: 30px; }}
  .header h1 {{ font-size: 1.8em; color: #38bdf8; }}
  .header .subtitle {{ color: #94a3b8; margin-top: 5px; }}
  .stats {{ display: flex; gap: 20px; justify-content: center; margin: 15px 0; }}
  .stat {{ background: #1e293b; padding: 8px 16px; border-radius: 8px; }}
  .stat strong {{ color: #38bdf8; }}
  .section {{ margin-bottom: 40px; }}
  .section h2 {{ font-size: 1.4em; color: #f8fafc; margin-bottom: 15px;
                 border-bottom: 2px solid #334155; padding-bottom: 8px; }}
  .section .count {{ color: #64748b; font-weight: normal; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
           gap: 16px; }}
  .card {{ background: #1e293b; border-radius: 12px; overflow: hidden;
           transition: transform 0.2s, box-shadow 0.2s; }}
  .card:hover {{ transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0,0,0,0.3); }}
  .card-link {{ text-decoration: none; color: inherit; display: block; }}
  .card-img {{ height: 180px; background: #0f172a; display: flex;
               align-items: center; justify-content: center; overflow: hidden; }}
  .card-img img {{ max-height: 100%; max-width: 100%; object-fit: contain; }}
  .card-body {{ padding: 12px 16px; }}
  .card-title {{ font-size: 0.9em; line-height: 1.3; height: 2.6em;
                 overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2;
                 -webkit-box-orient: vertical; }}
  .card-prices {{ margin: 8px 0; }}
  .price-current {{ font-size: 1.3em; font-weight: bold; color: #22c55e; }}
  .price-retail {{ color: #64748b; text-decoration: line-through; margin-left: 8px; font-size: 0.9em; }}
  .card-meta {{ display: flex; flex-wrap: wrap; gap: 6px; align-items: center; font-size: 0.8em; }}
  .badge {{ padding: 2px 8px; border-radius: 4px; color: #fff; font-weight: 600; font-size: 0.85em; }}
  .bids {{ color: #94a3b8; }}
  .closes {{ color: #94a3b8; }}
</style>
</head>
<body>
  <div class="header">
    <h1>Nellis Auction Finds</h1>
    <div class="subtitle">Katy, TX - {now.strftime("%B %d, %Y %I:%M %p")}</div>
    <div class="stats">
      <div class="stat"><strong>{len(items) + len(crazy_items)}</strong> new finds</div>
      <div class="stat"><strong>{stats["total"]}</strong> total tracked</div>
      <div class="stat"><strong>{stats["interesting"]}</strong> interesting</div>
    </div>
  </div>
  {sections_html}
</body>
</html>"""

    filename = f"report-{date_str}.html"
    filepath = os.path.join(config.REPORTS_DIR, filename)
    with open(filepath, "w") as f:
        f.write(html)

    # Mark items as notified (both regular and crazy deals)
    all_notified_ids = [item["id"] for item in items] + [item["id"] for item in crazy_items]
    if all_notified_ids:
        db.mark_notified(all_notified_ids)

    print(f"[report] Report saved to {filepath}")
    return filepath


if __name__ == "__main__":
    generate_report()
