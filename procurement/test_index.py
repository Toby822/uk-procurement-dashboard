"""Check cursor retries, release identity and transactional rollback."""
import unittest

from procurement.index import apply_page, connect, history, state


def release(id="one", date="2025-07-09T14:15:22+01:00"):
    return {"ocid": "sample", "id": id, "date": date, "tag": ["award"]}


def page(cursor, *releases):
    return {"source": cursor, "page": {"releases": releases}}


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.db = connect(":memory:")
        self.addCleanup(self.db.close)

    def test_retry_and_overlapping_pages(self):
        original = page("first", release())
        self.assertTrue(apply_page(self.db, original))
        self.assertFalse(apply_page(self.db, original))
        self.assertTrue(apply_page(self.db, page("next", release())))
        self.assertEqual(state(self.db)[0], 1)

    def test_changed_cursor_payload_is_rejected(self):
        apply_page(self.db, page("first", release()))
        with self.assertRaisesRegex(ValueError, "Cached page content changed"):
            apply_page(self.db, page("first", release("two")))
        self.assertEqual(state(self.db)[0], 1)

    def test_reused_release_id_rolls_back_other_inserts(self):
        apply_page(self.db, page("first", release()))
        initial = state(self.db)
        changed = release(date="2025-07-10T14:15:22+01:00")
        with self.assertRaisesRegex(ValueError, "Release ID reused"):
            apply_page(self.db, page("next", release("two"), changed))
        self.assertEqual(state(self.db), initial)

    def test_cutoff_uses_absolute_time_and_includes_equal_timestamp(self):
        apply_page(self.db, page("first", release()))
        self.assertEqual(history(self.db, "sample", "2025-07-09T13:15:21Z"), [])
        self.assertEqual(history(self.db, "sample", "2025-07-09T13:15:22Z"), [release()])


if __name__ == "__main__":
    unittest.main()
