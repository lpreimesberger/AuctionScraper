"""Woot classifier: keyword prescreen + Ollama verify for woot_interests.txt, plus stock-up keyword matching."""
import os
import re
from collections import defaultdict

import config
import woot_db
from classifier import INTEREST_KEYWORDS, is_excluded, verify_batch, fuzzy_match


def _load_lines(path: str) -> list[str]:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]


def load_interests() -> list[str]:
    return _load_lines(config.WOOT_INTERESTS_FILE)


def load_excludes() -> list[str]:
    return [t.lower() for t in _load_lines(config.WOOT_EXCLUDE_FILE)]


def load_stockup() -> list[str]:
    return _load_lines(config.WOOT_STOCKUP_FILE)


def _text(offer: dict) -> str:
    return f"{offer['title']} {offer.get('subtitle') or ''}".strip()


def patterns_for(interest: str) -> list[str]:
    """Reuse the Nellis keyword patterns where they exist; otherwise match the interest phrase itself."""
    return INTEREST_KEYWORDS.get(interest) or [r"\b" + re.escape(interest) + r"s?\b"]


def matches_stockup(offer: dict, terms: list[str]) -> bool:
    text = _text(offer)
    for t in terms:
        if re.search(r"\b" + re.escape(t) + r"s?\b", text, re.IGNORECASE) or fuzzy_match(t, text):
            return True
    return False


def prescreen(offers: list[dict], interests: list[str]) -> dict[str, list[dict]]:
    candidates = defaultdict(list)
    compiled = {i: [re.compile(p, re.IGNORECASE) for p in patterns_for(i)] for i in interests}
    for offer in offers:
        text = _text(offer)
        for interest, pats in compiled.items():
            if any(p.search(text) for p in pats) or fuzzy_match(interest, text):
                candidates[interest].append(offer)
    return dict(candidates)


def classify(batch_size: int = 25):
    interests = load_interests()
    offers = woot_db.get_unclassified()
    if not offers:
        print("[woot-classifier] No unclassified offers.")
        return
    excludes = load_excludes()
    excluded = [o for o in offers if is_excluded(o["title"], excludes)]
    offers = [o for o in offers if not is_excluded(o["title"], excludes)]
    if excluded:
        woot_db.mark_classified([o["offer_id"] for o in excluded])

    candidates = prescreen(offers, interests)
    candidate_ids = {o["offer_id"] for lst in candidates.values() for o in lst}
    non_candidates = [o["offer_id"] for o in offers if o["offer_id"] not in candidate_ids]
    woot_db.mark_classified(non_candidates)
    print(f"[woot-classifier] {len(candidate_ids)} candidates of {len(offers)} new offers; verifying with Ollama...")

    verified, failed = set(), set()
    for interest, lst in sorted(candidates.items(), key=lambda kv: -len(kv[1])):
        lst = [o for o in lst if o["offer_id"] not in verified]
        for b in range(0, len(lst), batch_size):
            batch = lst[b:b + batch_size]
            try:
                confirmed = verify_batch(interest, [{"title": _text(o)} for o in batch])
            except Exception as e:
                print(f"[woot-classifier] [{interest}] ERROR: {e}")
                failed.update(o["offer_id"] for o in batch)
                continue
            for idx in confirmed:
                woot_db.mark_classified([batch[idx]["offer_id"]], interest)
                verified.add(batch[idx]["offer_id"])
    # Candidates Ollama rejected are done; ones whose batch errored stay unclassified and retry next run.
    rejected = list(candidate_ids - verified - failed)
    woot_db.mark_classified(rejected)
    print(f"[woot-classifier] Done. {len(verified)} interesting offers found.")


if __name__ == "__main__":
    classify()
