"""Comentários opcionais: planos locais e AniList fictício, sem publicações reais."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sync_anilist as s
import plan_editor as editor
from review_pane import ReviewPane
from test_sync import FakeAL, entry, group, mapping, media


def sample():
    before = entry(progress=1)
    before["private"] = False
    plan = s.build_plan([group([1, 2])], [before], {10: media()}, mapping(), {"id": 1, "name": "demo"})
    return editor.set_activity_comment(plan, 10, "O que vem a seguir???"), before


def activity(progress="2", **fields):
    return {"id": 51, "userId": 1, "type": "ANIME_LIST", "media": {"id": 10},
            "progress": progress, "status": "watched episode", "isLocked": False, **fields}


class CommentAL(FakeAL):
    def __init__(self, before, outcome="ok"):
        super().__init__([before])
        self.before_activity = [activity("1", id=50)]
        self.after_activity = [activity()]
        self.replies = []
        self.reply_calls = 0
        self.activity_calls = 0
        self.outcome = outcome

    def activities(self, media_id):
        self.activity_calls += 1
        return copy.deepcopy(self.after_activity if self.calls else self.before_activity)

    def activity_replies(self, activity_id):
        return copy.deepcopy(self.replies)

    def reply_activity(self, activity_id, text):
        self.reply_calls += 1
        reply = {"id": 100 + self.reply_calls, "activityId": activity_id, "userId": 1, "text": text}
        if self.outcome != "lost":
            self.replies.append(reply)
        if self.outcome != "ok":
            raise s.ApiError("connection lost")
        return copy.deepcopy(reply)


class CommentPlanTests(unittest.TestCase):
    def test_only_exactly_one_episode_accepts_comment(self):
        plan, _ = sample()
        for delta in (0, 2, 10):
            bad = copy.deepcopy(plan)
            bad["changes"][0]["after"]["progress"] = 1 + delta
            with self.subTest(delta=delta), self.assertRaises(s.SyncError):
                editor.set_activity_comment(bad, 10, "Comentário")
        for invalid in ("a", "x" * 8001, None):
            with self.subTest(text_type=type(invalid)), self.assertRaises(s.SyncError):
                editor.set_activity_comment(plan, 10, invalid)
        blank = editor.set_activity_comment(plan, 10, " \n ")
        self.assertNotIn("activity_comment", blank["changes"][0])
        self.assertIn("activity_comment", plan["changes"][0])

    def test_comment_survives_selection_and_review_export_without_changing_notes(self):
        plan, before = sample()
        with tempfile.TemporaryDirectory() as folder:
            selected = editor.save_review(folder, plan, {10})
            stored = s.load_json(Path(folder) / "plano-revisado.json")
            self.assertEqual(stored["changes"][0]["activity_comment"], "O que vem a seguir???")
            self.assertIn("O que vem a seguir???", (Path(folder) / "alteracoes-revisadas.csv").read_text(encoding="utf-8-sig"))
        self.assertEqual(s.protected(selected["changes"][0]["before"]), s.protected(before))
        self.assertEqual(editor.selected_plan(plan, set())["changes"], [])

    def test_changed_progress_and_next_episode_do_not_reuse_comment(self):
        plan, before = sample()
        plan["changes"][0]["suggested_after"] = {"status": "COMPLETED", "progress": 3}
        changed = editor.edit_change(plan, 10, "COMPLETED", 3)
        self.assertNotIn("activity_comment", changed["changes"][0])
        confirmed = {**before, "progress": 2}
        remaining, base, _ = editor.consume_verified(plan, plan, {10}, [confirmed])
        self.assertEqual(remaining["changes"][0]["after"]["progress"], 3)
        self.assertNotIn("activity_comment", remaining["changes"][0])
        self.assertNotIn("activity_comment", base["changes"][0])


class CommentApplyTests(unittest.TestCase):
    def test_publishes_after_progress_verified_and_never_repeats_when_reapplied(self):
        plan, before = sample()
        al = CommentAL(before)
        with tempfile.TemporaryDirectory() as folder:
            first = s.apply_plan(al, plan, folder)
            journal = [json.loads(line) for line in (Path(folder) / "diario-aplicacao.jsonl").read_text(encoding="utf-8").splitlines()]
            second = s.apply_plan(al, plan, folder)
        self.assertEqual(first["comments"][0]["status"], "published")
        self.assertEqual(first["comments"][0]["activityId"], 51)
        self.assertEqual([row["phase"] for row in journal], ["attempt", "confirmed", "comment_attempt", "comment_result"])
        self.assertEqual(al.reply_calls, 1)
        self.assertEqual(al.calls, 1)
        self.assertEqual(second["comments"][0]["status"], "pending")
        self.assertEqual(s.protected(al.state[10]), s.protected(before))

    def test_missing_ambiguous_wrong_locked_and_old_activities_are_not_used(self):
        for activities in ([], [activity(), activity(id=52)], [activity(userId=2)],
                           [activity(media={"id": 20})], [activity(isLocked=True)],
                           [activity("1", id=50)], [activity("5")]):
            plan, before = sample()
            al = CommentAL(before)
            al.after_activity = activities
            with self.subTest(activities=activities), tempfile.TemporaryDirectory() as folder:
                result = s.apply_plan(al, plan, folder)
            self.assertTrue(result["success"])
            self.assertEqual(result["comments"][0]["status"], "pending")
            self.assertEqual(al.reply_calls, 0)
            self.assertEqual(al.http.wait.call_count, 2)

    def test_merged_activity_updated_in_place_is_found(self):
        plan, before = sample()
        al = CommentAL(before)
        al.after_activity = [activity("1 - 2", id=50)]
        with tempfile.TemporaryDirectory() as folder:
            result = s.apply_plan(al, plan, folder)
        self.assertEqual(result["comments"][0]["activityId"], 50)
        self.assertEqual(al.reply_calls, 1)

    def test_final_episode_can_comment_on_completion_activity(self):
        plan, before = sample()
        before["progress"] = 2
        plan["changes"][0]["before"] = copy.deepcopy(before)
        plan["changes"][0]["after"] = {"status": "COMPLETED", "progress": 3}
        al = CommentAL(before)
        al.after_activity = [activity(None, status="completed")]
        with tempfile.TemporaryDirectory() as folder:
            result = s.apply_plan(al, plan, folder)
        self.assertEqual(result["comments"][0]["status"], "published")

    def test_uncertain_publication_is_checked_without_resending(self):
        for outcome, expected in (("disconnect", "published"), ("lost", "unconfirmed")):
            plan, before = sample()
            al = CommentAL(before, outcome=outcome)
            # Uma resposta idêntica antiga não confirma uma nova tentativa.
            al.replies = [{"id": 99, "userId": 1, "text": plan["changes"][0]["activity_comment"]}]
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as folder:
                result = s.apply_plan(al, plan, folder)
                saved = s.load_json(Path(folder) / "comentarios.json")
            self.assertEqual(result["comments"][0]["status"], expected)
            self.assertEqual(saved, result["comments"])
            self.assertEqual(al.reply_calls, 1)
            self.assertTrue(result["success"])

    def test_no_comment_means_no_extra_api_calls(self):
        plan, before = sample()
        plan = editor.set_activity_comment(plan, 10, "")
        al = CommentAL(before)
        with tempfile.TemporaryDirectory() as folder:
            result = s.apply_plan(al, plan, folder)
        self.assertEqual(result["comments"], [])
        self.assertEqual(al.activity_calls, 0)
        self.assertEqual(al.reply_calls, 0)

    def test_invalid_comment_is_rejected_before_list_mutation(self):
        plan, before = sample()
        plan["changes"][0]["after"]["progress"] = 3
        al = CommentAL(before)
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(s.SyncError):
            s.apply_plan(al, plan, folder)
        self.assertEqual(al.calls, 0)
        self.assertEqual(al.reply_calls, 0)

    def test_snapshot_failure_keeps_comment_pending_but_updates_progress(self):
        plan, before = sample()
        al = CommentAL(before)
        al.activities = Mock(side_effect=s.ApiError("unavailable"))
        with tempfile.TemporaryDirectory() as folder:
            result = s.apply_plan(al, plan, folder)
        self.assertTrue(result["success"])
        self.assertEqual(result["comments"][0]["status"], "pending")
        self.assertEqual(al.reply_calls, 0)

    def test_api_comment_uses_variables_and_separate_mutation(self):
        al = s.AniList("fake")
        al.gql = Mock(return_value={"SaveActivityReply": {"id": 123}})
        text = 'Texto "com aspas"\n![](https://example.invalid/image.png)'
        al.reply_activity(51, text)
        query, variables = al.gql.call_args.args
        self.assertNotIn(text, query)
        self.assertIn("SaveActivityReply", query)
        self.assertEqual(variables, {"id": 51, "text": text})
        self.assertTrue(al.gql.call_args.kwargs["mutation"])


class CommentUiTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.pane = ReviewPane(self.root, Mock())
        self.plan, _ = sample()
        self.pane.load(self.plan)
        self.pane.table.selection_set("10")

    def test_comment_editor_saves_only_local_draft_and_table_shows_it(self):
        self.pane.comment_selected()
        dialog = next(w for w in self.pane.winfo_children() if isinstance(w, tk.Toplevel))
        outer = dialog.winfo_children()[0]
        text = next(w for w in outer.winfo_children() if isinstance(w, tk.Text))
        self.assertEqual(str(text.cget("state")), "normal")
        text.delete("1.0", "end")
        text.insert("1.0", "Novo comentário!")
        button = next(w for row in outer.winfo_children() for w in row.winfo_children()
                      if w.winfo_class() == "TButton" and w.cget("text") == "Salvar no plano")
        button.invoke()
        self.assertEqual(self.pane.plan["changes"][0]["activity_comment"], "Novo comentário!")
        self.assertEqual(self.pane.table.set("10", "comment"), "Novo comentário!")
        self.assertEqual(self.plan["changes"][0]["activity_comment"], "O que vem a seguir???")

    def test_multiple_episode_update_cannot_open_comment_shortcut(self):
        self.pane.plan["changes"][0]["after"]["progress"] = 3
        with patch("review_pane.messagebox.showinfo") as info:
            self.pane.comment_selected()
        info.assert_called_once()
        self.assertFalse(any(isinstance(w, tk.Toplevel) for w in self.pane.winfo_children()))
