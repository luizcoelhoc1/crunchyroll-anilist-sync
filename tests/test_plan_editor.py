import copy
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import plan_editor as e
import sync_anilist as s
from test_sync import FakeAL, entry, group, media, mapping


def sample_plan():
    entries = [entry(10, progress=1), entry(20, progress=0)]
    groups = [group([1, 2, 3], key="A"), group([1, 2, 3], key="B")]
    rules = {"groups": {"A": {"rules": [{"mediaId": 10}]},
                        "B": {"rules": [{"mediaId": 20}]}}}
    plan = s.build_plan(groups, entries, {10: media(10), 20: media(20)}, rules,
                        {"id": 1, "name": "demo"})
    return plan, entries


class PlanReviewTests(unittest.TestCase):
    def test_subset_only_contains_marked_items_and_keeps_original(self):
        plan, _ = sample_plan()
        selected = e.selected_plan(plan, {20})
        self.assertEqual([c["mediaId"] for c in selected["changes"]], [20])
        self.assertEqual(selected["summary"]["changes"], 1)
        self.assertEqual(len(plan["changes"]), 2)
        self.assertEqual(selected["selection"]["deferred"], [10])

    def test_unknown_selection_is_refused(self):
        plan, _ = sample_plan()
        with self.assertRaises(s.SyncError):
            e.selected_plan(plan, {999})

    def test_exclusion_only_removes_from_local_plan(self):
        plan, _ = sample_plan()
        result = e.remove_changes(plan, {10})
        self.assertEqual([c["mediaId"] for c in result["changes"]], [20])
        self.assertEqual(len(plan["changes"]), 2)
        self.assertEqual(result["review_actions"][0]["action"], "exclude_from_plan")

    def test_edit_partial_keeps_confirmed_ceiling_across_multiple_edits(self):
        plan, _ = sample_plan()
        first = e.edit_change(plan, 10, "CURRENT", 2)
        second = e.edit_change(first, 10, "COMPLETED", 3)
        self.assertEqual(first["changes"][0]["suggested_after"]["progress"], 3)
        self.assertEqual(second["changes"][0]["after"]["progress"], 3)
        self.assertEqual(plan["changes"][0]["after"]["status"], "COMPLETED")

    def test_progress_cannot_regress_or_exceed_evidence(self):
        plan, _ = sample_plan()
        for progress in (0, 4, True, 1.2):
            with self.subTest(progress=progress), self.assertRaises(s.SyncError):
                e.edit_change(plan, 10, "CURRENT", progress)

    def test_incomplete_progress_cannot_be_completed(self):
        plan, _ = sample_plan()
        with self.assertRaises(s.SyncError):
            e.edit_change(plan, 10, "COMPLETED", 2)

    def test_planning_requires_zero_progress(self):
        plan, _ = sample_plan()
        with self.assertRaises(s.SyncError):
            e.edit_change(plan, 10, "PLANNING", 2)

    def test_edits_preserve_baseline_protected_fields(self):
        plan, _ = sample_plan()
        edited = e.edit_change(plan, 10, "PAUSED", 2)
        self.assertEqual(edited["changes"][0]["before"], plan["changes"][0]["before"])
        self.assertEqual(s.protected(edited["changes"][0]["before"]),
                         s.protected(plan["changes"][0]["before"]))

    def test_partial_application_does_not_touch_unmarked_entry(self):
        plan, entries = sample_plan()
        al = FakeAL(entries)
        selected = e.selected_plan(e.edit_change(plan, 10, "CURRENT", 2), {10})
        with tempfile.TemporaryDirectory() as folder:
            result = s.apply_plan(al, selected, folder)
        self.assertEqual(al.calls, 1)
        self.assertEqual(al.state[10]["progress"], 2)
        self.assertEqual(al.state[20], entries[1])
        self.assertEqual(result["confirmed_entries"][0]["mediaId"], 10)
        self.assertEqual(s.protected(al.state[10]), s.protected(entries[0]))

    def test_second_batch_can_apply_remaining_entry(self):
        plan, entries = sample_plan()
        al = FakeAL(entries)
        with tempfile.TemporaryDirectory() as folder:
            first = s.apply_plan(al, e.selected_plan(plan, {10}), Path(folder)/"lote1")
            second = s.apply_plan(al, e.selected_plan(plan, {20}), Path(folder)/"lote2")
        self.assertTrue(first["success"] and second["success"])
        self.assertEqual(al.calls, 2)
        self.assertEqual([al.state[i]["progress"] for i in (10, 20)], [3, 3])

    def test_partial_progress_returns_remainder_with_fresh_baseline(self):
        plan, entries = sample_plan()
        partial = e.edit_change(plan, 10, "CURRENT", 2)
        al = FakeAL(entries)
        with tempfile.TemporaryDirectory() as folder:
            result = s.apply_plan(al, e.selected_plan(partial, {10}), folder)
        remaining, original, finished = e.consume_verified(
            partial, plan, {10}, result["confirmed_entries"])
        c = remaining["changes"][0]
        self.assertEqual(c["before"]["progress"], 2)
        self.assertEqual(c["after"], {"status": "COMPLETED", "progress": 3})
        self.assertTrue(c["continuation"])
        self.assertEqual(finished, set())
        self.assertEqual(original["changes"][0]["before"]["progress"], 2)
        with tempfile.TemporaryDirectory() as folder:
            final = s.apply_plan(al, e.selected_plan(remaining, {10}), folder)
        self.assertTrue(final["success"])
        self.assertEqual(al.state[10]["progress"], 3)

    def test_fully_applied_entry_is_finished_not_requeued(self):
        plan, entries = sample_plan()
        al = FakeAL(entries)
        with tempfile.TemporaryDirectory() as folder:
            result = s.apply_plan(al, e.selected_plan(plan, {10}), folder)
        remaining, _, finished = e.consume_verified(plan, plan, {10}, result["confirmed_entries"])
        self.assertEqual([c["mediaId"] for c in remaining["changes"]], [20])
        self.assertEqual(finished, {10})

    def test_review_state_file_cannot_apply_unchecked_rows(self):
        plan, entries = sample_plan()
        with tempfile.TemporaryDirectory() as folder:
            e.save_review(folder, plan, {10})
            state = s.load_json(Path(folder)/"revisao.json")
            al = FakeAL(entries)
            with self.assertRaises(s.SyncError):
                s.apply_plan(al, state, folder)
            self.assertEqual(al.calls, 0)

    def test_exported_apply_plan_excludes_unchecked_rows(self):
        plan, _ = sample_plan()
        with tempfile.TemporaryDirectory() as folder:
            e.save_review(folder, plan, (i for i in [10]))
            apply_plan = s.load_json(Path(folder)/"plano-revisado.json")
            state = s.load_json(Path(folder)/"revisao.json")
            with (Path(folder)/"alteracoes-revisadas.csv").open(encoding="utf-8-sig") as stream:
                csv_rows = list(csv.reader(stream, delimiter=";"))
        self.assertEqual([c["mediaId"] for c in apply_plan["changes"]], [10])
        self.assertEqual(len(state["changes"]), 2)
        self.assertEqual([r[0] for r in csv_rows[1:]], ["Sim", "Nao"])


if __name__ == "__main__":
    unittest.main()
