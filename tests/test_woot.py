import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import woot_classifier
import woot_db
import woot_report


def feed_item(oid, title, list_p, sale_p, **kw):
    item = {
        "OfferId": oid, "Title": title, "Subtitle": None, "Condition": None, "Site": "Home & Kitchen",
        "Categories": ["X"], "Photo": "http://p/x.png", "Url": f"http://woot/{oid}",
        "EndDate": "2999-01-01T00:00:00+00:00", "IsSoldOut": False,
        "ListPrice": {"Minimum": list_p, "Maximum": list_p} if list_p else None,
        "SalePrice": {"Minimum": sale_p, "Maximum": sale_p},
    }
    item.update(kw)
    return item


class WootTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        config.WOOT_DB_PATH = os.path.join(self.tmp, "woot.db")
        woot_db.init_db()

    def test_parse_and_discount(self):
        row = woot_db.parse_offer(feed_item("a", "Thing", 100.0, 20.0, Condition="Refurbished "))
        self.assertEqual(row["condition"], "Refurbished")
        self.assertAlmostEqual(woot_db.discount(row), 0.8)
        self.assertAlmostEqual(woot_db.savings(row), 80.0)

    def test_missing_list_price_is_zero_discount(self):
        row = woot_db.parse_offer(feed_item("a", "Thing", None, 20.0))
        self.assertIsNone(row["list_min"])
        self.assertEqual(woot_db.discount(row), 0.0)

    def test_sync_prunes_but_never_on_empty_feed(self):
        rows = [woot_db.parse_offer(feed_item(i, i, 10, 5)) for i in "abc"]
        self.assertEqual(woot_db.sync_offers(rows), (3, 0))
        self.assertEqual(woot_db.sync_offers(rows[:2]), (0, 1))
        self.assertEqual(woot_db.sync_offers([]), (0, 0))
        self.assertEqual(woot_db.get_stats()["total"], 2)

    def test_sync_preserves_notified_flag(self):
        row = woot_db.parse_offer(feed_item("a", "Thing", 10, 5))
        woot_db.sync_offers([row])
        woot_db.mark_notified(["a"])
        woot_db.sync_offers([row])
        self.assertEqual(woot_db.get_unnotified(), [])

    def test_expire_ended(self):
        row = woot_db.parse_offer(feed_item("a", "Thing", 10, 5, EndDate="2001-01-01T00:00:00+00:00"))
        woot_db.sync_offers([row])
        self.assertEqual(woot_db.expire_ended(), 1)

    def test_prescreen_uses_nellis_patterns_and_falls_back_to_phrase(self):
        offers = [{"offer_id": "1", "title": "Cordless Drill Kit", "subtitle": None},
                  {"offer_id": "2", "title": "Sun Shade Sail", "subtitle": None},
                  {"offer_id": "3", "title": "Coffee Table", "subtitle": None}]
        c = woot_classifier.prescreen(offers, ["power tools", "shade"])
        self.assertEqual([o["offer_id"] for o in c["power tools"]], ["1"])
        self.assertEqual([o["offer_id"] for o in c["shade"]], ["2"])

    def test_sections(self):
        def row(oid, title, lp, sp, interest=None):
            r = woot_db.parse_offer(feed_item(oid, title, lp, sp))
            r["interest_match"] = interest
            return r
        offers = [
            row("int", "Cool Gadget", 100, 90, "coffee"),
            row("sock", "Wool Socks 6-pack", 30, 12),            # 60% off, stockup
            row("sockweak", "Cotton Socks", 30, 25),            # 17% off, not shown
            row("crazy", "Big Thing", 500, 50),                 # 90% off
            row("cheap", "Tiny Thing", 10, 1),                  # below min list
            row("inv", "Invicta Watch", 1000, 80),              # excluded
            row("mid", "Mid Thing", 100, 50),                   # 50% off, not crazy
        ]
        s = woot_report.select_sections(offers, ["invicta"], ["socks"])
        self.assertEqual([o["offer_id"] for o in s["interesting"]], ["int"])
        self.assertEqual([o["offer_id"] for o in s["stockup"]], ["sock"])
        self.assertEqual([o["offer_id"] for o in s["crazy"]], ["crazy"])

    def test_card_escapes_html(self):
        r = woot_db.parse_offer(feed_item("a", "<script>x</script> & co", 10, 5))
        self.assertNotIn("<script>", woot_report.generate_item_card(r))


if __name__ == "__main__":
    unittest.main()
