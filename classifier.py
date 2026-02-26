import json
import os
import re
from collections import defaultdict

import ollama

import config
import db


def load_interests() -> list[str]:
    with open(config.INTERESTS_FILE) as f:
        return [line.strip() for line in f if line.strip()]


def load_excludes() -> list[str]:
    if not os.path.exists(config.EXCLUDE_FILE):
        return []
    with open(config.EXCLUDE_FILE) as f:
        return [line.strip().lower() for line in f if line.strip()]


def is_excluded(title: str, excludes: list[str]) -> bool:
    """Quick keyword pre-filter: skip items that match exclusion terms."""
    title_lower = title.lower()
    return any(term in title_lower for term in excludes)


# Keyword patterns for each interest. These are used for pre-screening candidates.
# The LLM then verifies each candidate to filter false positives.
INTEREST_KEYWORDS = {
    "tools": [
        r"\btool\b", r"\bwrench", r"\bplier", r"\bscrewdriver", r"\bhammer\b",
        r"\bsocket set", r"\bratchet\b", r"\bhex key", r"\btape measure",
        r"\blevel\b", r"\bchisel", r"\bvise\b", r"\bmultimeter", r"\bwire stripper",
        r"\bcrimper", r"\btorque", r"\bknife\b", r"\bblade\b", r"\butility knife",
    ],
    "tents": [r"\btent\b", r"\btents\b", r"\bcanopy\b", r"\bgazebo\b"],
    "RV parts": [
        r"\bRV\b", r"\bmotorhome", r"\bcamper\b", r"\btrailer hitch",
        r"\bleveling jack", r"\bsewer hose", r"\bfifth wheel",
    ],
    "camping gear": [
        r"\bcamping\b", r"\bcamp stove", r"\bcampfire", r"\bsleeping bag",
        r"\bcamp chair", r"\bcamp cot", r"\bheadlamp", r"\blantern\b",
        r"\bportable grill", r"\bcooler\b", r"\bcamp mug", r"\bbackpack",
        r"\bhiking\b",
    ],
    "power tools": [
        r"\bdrill\b", r"\bsaw\b", r"\bsander\b", r"\bgrinder\b", r"\bjigsaw",
        r"\brouter\b", r"\bimpact driver", r"\bangle grinder", r"\bnail gun",
        r"\bheat gun", r"\brotary tool", r"\boscillating", r"\bplaner\b",
        r"\bcordless.*(?:drill|saw|driver|grinder)",
    ],
    "generators": [r"\bgenerator", r"\bpower station\b", r"\binverter generator"],
    "welding": [
        r"\bweld", r"\bwelder\b", r"\bmig\b", r"\btig\b", r"\bflux.core",
        r"\bwelding",
    ],
    "outdoor furniture": [
        r"\bpatio\b", r"\boutdoor furniture", r"\badirondack", r"\bfire pit",
        r"\boutdoor bench", r"\bpergola\b", r"\boutdoor dining", r"\boutdoor table",
        r"\bgarden furniture", r"\bdeck chair",
    ],
    "Stage Lighting": [
        r"\bstage light", r"\bpar light", r"\bDMX\b", r"\bmoving head",
        r"\bwash light", r"\bgobo\b", r"\btheater light", r"\bstage effect",
    ],
    "Switches": [
        r"\bswitch\b", r"\bswitches\b", r"\btoggle switch", r"\brocker switch",
        r"\bdimmer switch", r"\brelay\b", r"\bcircuit breaker",
    ],
    "Burr Grinders": [r"\bburr grinder", r"\bcoffee grinder", r"\bespresso grinder"],
    "coffee": [
        r"\bcoffee maker", r"\bcoffee machine", r"\bespresso\b", r"\bfrench press",
        r"\bpour over\b", r"\bcoffee bean", r"\bmoka pot", r"\baeropress",
        r"\bchemex\b", r"\bcoffee brew", r"\bcoffee\b",
    ],
    "Plotter": [
        r"\bplotter", r"\bcutting plotter", r"\bvinyl cutter",
        r"\bwide.format printer", r"\bdesignjet\b",
    ],
    "bandsaw": [r"\bbandsaw", r"\bband saw"],
    "awning": [r"\bawning", r"\bretractable shade"],
    "Computers": [
        r"\bcomputer\b", r"\blaptop\b", r"\bdesktop pc", r"\bchromebook",
        r"\bmini pc\b", r"\bworkstation\b", r"\bnotebook\b",
    ],
    "Heavy Duty Casters": [r"\bcaster", r"\bcasters\b"],
    "spotlight": [r"\bspotlight", r"\bspot light", r"\bflood.?light", r"\bsearch.?light"],
    "bulk": [r"\bbulk lot", r"\bwholesale lot", r"\bbulk pack"],
    "lot": [r"\blot of \d+", r"\d+\s*(?:pc|pcs|piece|pieces)\s"],
    "solar": [r"\bsolar\b"],
    "pipe": [
        r"\bpvc pipe", r"\bcopper pipe", r"\bsteel pipe", r"\bpipe fitting",
        r"\bpipe wrench", r"\bpipe cutter", r"\bgalvanized pipe", r"\biron pipe",
        r"\bpipe\b",
    ],
    "DMX512": [r"\bDMX.?512", r"\bDMX controller", r"\bDMX cable", r"\bDMX splitter"],
}


SYSTEM_PROMPT = """You verify auction item classifications. Given items pre-matched to an interest category, confirm which ones truly belong.
Rules:
- "coffee table" is NOT coffee, "machine washable" is NOT machines, "No Drill blinds" is NOT drills
- Kids toy/pretend versions don't count (toy tool set is NOT tools)
- The item must BE the thing, not just mention it
- Match the CORE product purpose only"""


def keyword_prescreening(items: list[dict], interests: list[str]) -> dict[str, list[dict]]:
    """Pre-screen items using keyword patterns. Returns {interest: [items]} candidates."""
    candidates = defaultdict(list)
    # Only check interests that have keyword patterns
    active_interests = {i: INTEREST_KEYWORDS.get(i, []) for i in interests if i in INTEREST_KEYWORDS}

    for item in items:
        title = item["title"]
        for interest, patterns in active_interests.items():
            for pattern in patterns:
                if re.search(pattern, title, re.IGNORECASE):
                    candidates[interest].append(item)
                    break  # Don't double-count same item for same interest

    return dict(candidates)


def verify_batch(interest: str, items: list[dict]) -> list[int]:
    """Ask LLM to verify which items truly match the given interest.

    Returns list of 0-based indices of confirmed matches.
    """
    items_str = "\n".join(f"{i + 1}. {item['title'][:100]}" for i, item in enumerate(items))

    user_msg = f"""Which of these items are genuinely "{interest}"?
Only include items where {interest} is the CORE product purpose.

Items:
{items_str}

Return confirmed line numbers as JSON array: [1, 4, 7]
Return [] if none qualify.
JSON:"""

    response = ollama.chat(
        model=config.OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        options={"temperature": 0.1, "num_predict": 1024},
    )

    text = response["message"]["content"].strip()

    # Extract JSON array
    json_match = re.search(r'\[.*?\]', text, re.DOTALL)
    if not json_match:
        return []

    try:
        result = json.loads(json_match.group(0))
    except json.JSONDecodeError:
        print(f"\n[classifier] Warning: failed to parse verify response for '{interest}'")
        return []

    # Convert 1-based line numbers to 0-based indices
    confirmed = []
    for item in result:
        if isinstance(item, dict):
            n = item.get("n") or item.get("line")
            if n is not None:
                idx = int(n) - 1
                if 0 <= idx < len(items):
                    confirmed.append(idx)
        elif isinstance(item, (int, float)):
            idx = int(item) - 1
            if 0 <= idx < len(items):
                confirmed.append(idx)

    return confirmed


def classify():
    """Classify items using keyword pre-screening + LLM verification."""
    interests = load_interests()
    if not interests:
        print("[classifier] No interests found in interests.txt")
        return

    excludes = load_excludes()

    print(f"[classifier] Interests: {', '.join(interests)}")
    if excludes:
        print(f"[classifier] Excludes: {len(excludes)} terms from exclude.txt")

    items = db.get_unclassified_items()
    if not items:
        print("[classifier] No unclassified items to process.")
        return

    # Pre-filter: exclude items matching exclusion keywords
    if excludes:
        excluded_items = [item for item in items if is_excluded(item["title"], excludes)]
        items = [item for item in items if not is_excluded(item["title"], excludes)]
        if excluded_items:
            db.mark_not_interesting([item["id"] for item in excluded_items])
            print(f"[classifier] Pre-filtered: {len(excluded_items)} items excluded by keywords, {len(items)} remaining")

    # Phase 1: Keyword pre-screening
    print(f"[classifier] Phase 1: Keyword pre-screening {len(items)} items...")
    candidates = keyword_prescreening(items, interests)

    total_candidates = sum(len(v) for v in candidates.values())
    candidate_ids = set()
    for items_list in candidates.values():
        candidate_ids.update(item["id"] for item in items_list)
    print(f"[classifier] Found {len(candidate_ids)} unique candidate items across {len(candidates)} interests")
    for interest, items_list in sorted(candidates.items(), key=lambda x: -len(x[1])):
        print(f"[classifier]   {interest:25s}: {len(items_list)} candidates")

    # Mark non-candidates as not interesting
    all_ids = {item["id"] for item in items}
    non_candidate_ids = all_ids - candidate_ids
    if non_candidate_ids:
        db.mark_not_interesting(list(non_candidate_ids))
        print(f"[classifier] Marked {len(non_candidate_ids)} non-matching items as classified")

    # Phase 2: LLM verification
    print(f"\n[classifier] Phase 2: LLM verification of candidates...")
    batch_size = 25
    total_verified = 0
    verified_ids = set()  # Track which items have been verified for any interest

    for interest, interest_items in sorted(candidates.items(), key=lambda x: -len(x[1])):
        num_batches = (len(interest_items) + batch_size - 1) // batch_size
        interest_verified = 0

        for b in range(0, len(interest_items), batch_size):
            batch = interest_items[b:b + batch_size]
            batch_num = b // batch_size + 1
            print(
                f"[classifier] [{interest}] Batch {batch_num}/{num_batches} ({len(batch)} items)...",
                end=" ",
                flush=True,
            )

            try:
                confirmed_indices = verify_batch(interest, batch)
            except Exception as e:
                print(f"ERROR: {e}")
                continue

            for idx in confirmed_indices:
                item = batch[idx]
                if item["id"] not in verified_ids:
                    db.mark_interesting(item["id"], interest)
                    verified_ids.add(item["id"])
                    interest_verified += 1

            print(f"{len(confirmed_indices)} confirmed")

        if interest_verified > 0:
            total_verified += interest_verified
            print(f"[classifier] [{interest}] {interest_verified} items verified")

    # Mark remaining candidates that weren't verified as not interesting
    unverified_candidates = candidate_ids - verified_ids
    if unverified_candidates:
        db.mark_not_interesting(list(unverified_candidates))

    print(f"\n[classifier] Done. {total_verified} interesting items found.")


if __name__ == "__main__":
    classify()
