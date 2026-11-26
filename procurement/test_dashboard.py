"""Browser checks for the standalone procurement dashboard."""
from collections import Counter
import json
import os
from pathlib import Path
import sqlite3
import unittest

from playwright.sync_api import sync_playwright

DASHBOARD = Path("results/dashboard.html")
DB = Path("results/notices.sqlite3")


class DashboardTest(unittest.TestCase):
    def test_filters_and_publication_cutoff(self):
        with sqlite3.connect(DB) as db:
            rows = db.execute("SELECT published, tags FROM release").fetchall()
            date_counts = Counter(timestamp[:10] for timestamp, _ in rows)
            tag_counts = Counter(tag for _, tags in rows for tag in json.loads(tags))
            proc = db.execute(
                "SELECT ocid, MIN(published) FROM release GROUP BY ocid HAVING COUNT(*)>1 ORDER BY ocid LIMIT 1"
            ).fetchone()
            total, = db.execute("SELECT COUNT(DISTINCT ocid) FROM release").fetchone()
            history, = db.execute(
                "SELECT COUNT(*) FROM release WHERE ocid=? AND published<=?", proc
            ).fetchone()
        with sync_playwright() as playwright:
            executable = os.environ.get("CHROMIUM_EXECUTABLE")
            browser = playwright.chromium.launch(executable_path=executable, args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 390, "height": 844})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(DASHBOARD.resolve().as_uri())
            self.assertEqual(page.locator("#release-count").inner_text(), f"{len(rows):,}")
            self.assertEqual(page.locator("#process-count").inner_text(), f"{total:,}")
            self.assertEqual(page.locator("#dates .row").count(), len(date_counts))
            self.assertEqual(page.locator("#tags .row").count(), len(tag_counts))
            day = sorted(date_counts)[0]
            page.get_by_role("button", name=f"Filter by {day}").click()
            self.assertEqual(page.locator("#release-count").inner_text(), f"{date_counts[day]:,}")
            page.locator("#from").fill("")
            page.locator("#to").fill("")
            tag = tag_counts.most_common(1)[0][0]
            page.get_by_role("button", name=f"Filter by {tag}", exact=True).click()
            self.assertEqual(page.locator("#release-count").inner_text(), f"{tag_counts[tag]:,}")
            page.locator("#tag").select_option("")
            page.locator("#process").evaluate("(field, value) => { field.value = value; field.dispatchEvent(new Event('input', {bubbles: true})); }", proc[0])
            self.assertEqual(page.locator("#process").input_value(), proc[0])
            page.locator("#asof").fill(proc[1][:19])
            self.assertEqual(page.locator("#history tr").count(), history)
            page.get_by_role("button", name="Load a sample process").click()
            self.assertTrue(page.locator("#process").input_value())
            self.assertEqual(page.locator("#tag").input_value(), "")
            self.assertGreater(page.locator("#history tr").count(), 1)
            page.get_by_role("button", name="Clear filters").click()
            self.assertEqual(page.locator("#release-count").inner_text(), f"{len(rows):,}")
            page.locator("#process").fill("no-such-process")
            self.assertEqual(page.locator("#release-count").inner_text(), "0")
            self.assertEqual(page.locator("#status").inner_text(), "No notices match these filters.")
            page.get_by_role("button", name="Clear filters").click()
            self.assertEqual(page.evaluate("document.documentElement.scrollWidth"), 390)
            page.set_viewport_size({"width": 1440, "height": 900})
            self.assertEqual(page.evaluate("document.documentElement.scrollWidth"), 1440)
            self.assertEqual(errors, [])
            browser.close()
