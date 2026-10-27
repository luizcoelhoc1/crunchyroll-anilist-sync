import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
import urllib.error
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sync_anilist as s


def media(i=10, episodes=3, title="Example", fmt="TV"):
    return {"id": i, "type": "ANIME", "title": {"english": title, "romaji": title},
            "episodes": episodes, "format": fmt, "synonyms": [], "externalLinks": []}


def entry(i=10, progress=0, status="CURRENT"):
    return {"id": i + 1000, "mediaId": i, "status": status, "progress": progress,
            "score": 8.2, "repeat": 1, "private": True, "notes": "Preservar.",
            "hiddenFromStatusLists": False, "customLists": {"Minha lista": True},
            "advancedScores": {"Roteiro": 7}, "startedAt": {"year": 2024, "month": 2, "day": 1},
            "completedAt": dict(s.EMPTY_DATE), "updatedAt": 0, "media": media(i)}


def group(numbers, partial=(), key="SERIES|S1"):
    return {"key": key, "title": "Example", "season": "Season 1", "sn": 1,
            "rows": [{"id": str(n), "full": n not in partial, "epText": str(n),
                      "ep": n, "seq": n, "title": "Episode", "versions": []} for n in numbers]}


def mapping(key="SERIES|S1", rules=None):
    return {"schema_version": 1, "groups": {key: {"rules": rules or [{"mediaId": 10}]}}}


def jwt(profile="active", expiry=None):
    import base64
    payload = {"exp": expiry or time.time() + 1000, "profile_id": profile,
               "scopes": {"cr": {"acc_id": "account"}}}
    enc = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return "header." + enc + ".fake-signature"


class RulesTests(unittest.TestCase):
    def plan(self, g, before=None, total=3):
        return s.build_plan([g], [] if before is None else [before], {10: media(10, total)},
                            mapping(), {"id": 1, "name": "demo"})

    def test_partial_episode_is_not_watched(self):
        p = self.plan(group([1, 2, 3], partial=[3]))
        self.assertEqual(p["changes"][0]["after"], {"status": "CURRENT", "progress": 2})

    def test_gap_prevents_false_completion(self):
        p = self.plan(group([1, 3]), total=3)
        self.assertEqual(p["changes"][0]["after"]["progress"], 1)
        self.assertEqual(p["pending"][0]["missing"], [2])

    def test_existing_progress_covers_history_gap(self):
        p = self.plan(group([3]), entry(progress=2))
        self.assertEqual(p["changes"][0]["after"], {"status": "COMPLETED", "progress": 3})

    def test_completed_entry_never_regresses(self):
        p = self.plan(group([1]), entry(progress=3, status="COMPLETED"))
        self.assertEqual(p["changes"], [])

    def test_higher_progress_is_preserved(self):
        p = self.plan(group([1]), entry(progress=2))
        self.assertEqual(p["changes"], [])

    def test_duplicate_audio_does_not_add_progress(self):
        g = group([1, 1, 2, 2])
        p = self.plan(g)
        self.assertEqual(p["changes"][0]["after"]["progress"], 2)

    def test_dropped_status_kept_for_partial_progress(self):
        p = self.plan(group([1, 2]), entry(progress=1, status="DROPPED"))
        self.assertEqual(p["changes"][0]["after"], {"status": "DROPPED", "progress": 2})

    def test_dropped_becomes_completed_with_full_evidence(self):
        p = self.plan(group([2, 3]), entry(progress=1, status="DROPPED"))
        self.assertEqual(p["changes"][0]["after"]["status"], "COMPLETED")

    def test_cours_split_cumulative_numbering(self):
        g = group([12, 13, 14])
        rules = [{"mediaId": 10, "lo": 12, "hi": 14, "offset": 11}]
        p = s.build_plan([g], [], {10: media()}, mapping(rules=rules), {"id": 1, "name": "demo"})
        self.assertEqual(p["changes"][0]["after"]["progress"], 3)

    def test_ova_is_separate_from_main_season(self):
        g = group([1, 2, 3])
        g["rows"][2].update(epText="OVA", title="Special")
        rules = [{"mediaId": 10, "hi": 2},
                 {"mediaId": 20, "mode": "one", "title": "^Special$"}]
        p = s.build_plan([g], [], {10: media(10, 2), 20: media(20, 1)},
                         mapping(rules=rules), {"id": 1, "name": "demo"})
        self.assertEqual([(c["mediaId"], c["after"]["progress"]) for c in p["changes"]], [(10, 2), (20, 1)])

    def test_conflicting_rules_rejected(self):
        with self.assertRaises(s.SyncError):
            s.build_plan([group([1])], [], {10: media(10), 20: media(20)},
                         mapping(rules=[{"mediaId": 10}, {"mediaId": 20}]), {"id": 1, "name": "demo"})

    def test_unmapped_extra_is_reported(self):
        p = s.build_plan([group([1, 2, 3])], [], {10: media(10, 2)},
                         mapping(rules=[{"mediaId": 10, "hi": 2}]), {"id": 1, "name": "demo"})
        self.assertTrue(any("fora das regras" in x["reason"] for x in p["pending"]))

    def test_unmapped_special_does_not_start_planned_season(self):
        p = self.plan(group([24]), entry(progress=0, status="PLANNING"))
        self.assertEqual(p["changes"], [])
        self.assertTrue(p["pending"])

    def test_streaming_link_alone_cannot_match_second_season(self):
        g = group([1])
        g["season"] = "Season 2"
        g["sn"] = 2
        m = media()
        m["streamingEpisodes"] = [{"url": "https://www.crunchyroll.com/watch/1"}]
        rule, reason = s.auto_rule(g, {10: m})
        self.assertIsNone(rule)

    def test_auto_exact_unique_first_season(self):
        rule, _ = s.auto_rule(group([1, 2]), {10: media()})
        self.assertEqual(rule["mediaId"], 10)

    def test_auto_rejects_source_covering_multiple_cours(self):
        rule, _ = s.auto_rule(group([1, 2, 3, 4]), {10: media(episodes=3)})
        self.assertIsNone(rule)


class AuthAndTransportTests(unittest.TestCase):
    def test_parse_fetch_without_executing_and_cookie_comment(self):
        text = '''// Originally called with XHR
fetch("https://anilist.co/graphql", {
  "headers": {
    "x-csrf-token": "fake-csrf",
    // "cookie": "fake_session=fake-value",
    "sec-fetch-site": "same-origin"
  },
  "method":"POST"
});'''
        url, headers = s.parse_fetch(text, "al")
        self.assertEqual(headers["cookie"], "fake_session=fake-value")
        self.assertNotIn("sec-fetch-site", headers)
        self.assertEqual(url, s.AL_WEB)

    def test_wrong_domain_rejected(self):
        with self.assertRaises(s.SyncError):
            s.parse_fetch('fetch("https://evil.example/graphql",{"headers":{}})', "al")

    def test_header_newline_rejected(self):
        with self.assertRaises(s.SyncError):
            s.parse_fetch('fetch("https://anilist.co/graphql",{"headers":{"cookie":"a\\r\\nb"}})', "al")

    def test_no_credential_redirects(self):
        client = s.HttpClient("https://anilist.co", {"cookie": "secret"})
        with self.assertRaises(s.SyncError):
            client._safe_url("https://evil.example/graphql")
        with self.assertRaises(s.ApiError):
            s.PinnedRedirect().redirect_request(None, None, 302, "", {}, "https://evil.example/")

    def test_mutation_transport_error_not_blindly_retried(self):
        client = s.HttpClient(s.AL_API)
        client.opener.open = Mock(side_effect=urllib.error.URLError("offline"))
        client.wait = lambda _: None
        with self.assertRaises(s.ApiError):
            client.request("POST", "/", {"query": "mutation{}"}, mutation=True)
        self.assertEqual(client.opener.open.call_count, 1)

    def test_query_transport_retry_is_bounded(self):
        client = s.HttpClient(s.AL_API)
        client.opener.open = Mock(side_effect=urllib.error.URLError("offline"))
        client.wait = lambda _: None
        with self.assertRaises(s.ApiError):
            client.request("POST", "/", {"query": "query{}"})
        self.assertEqual(client.opener.open.call_count, 4)

    def test_auth_error_does_not_expose_token(self):
        token = "example-secret-do-not-log"
        client = s.HttpClient(s.AL_API, {"Authorization": token})
        client.opener.open = Mock(side_effect=urllib.error.HTTPError(s.AL_API, 401, "", {}, io.BytesIO()))
        with self.assertRaises(s.ApiError) as ctx:
            client.request("POST", "/")
        self.assertNotIn(token, str(ctx.exception))

    def test_expired_cr_token_rejected(self):
        with self.assertRaises(s.SyncError):
            s.Crunchyroll(jwt(expiry=time.time()-100), profile="")

    def test_raw_page_with_next_cursor_rejected(self):
        with self.assertRaises(s.SyncError):
            s.normalize_history({"data": [], "meta": {"next_page": "/next"}})

    def test_cr_pagination_refuses_another_account(self):
        cr = s.Crunchyroll(jwt(), profile="")
        cr.http.request = Mock(return_value={"data": [], "meta": {
            "next_page": "/content/v2/OTHER/watch-history?page=2"}})
        with self.assertRaises(s.SyncError):
            cr.history()
        self.assertEqual(cr.http.request.call_count, 1)

    def test_profile_mismatch_rejected(self):
        cr = s.Crunchyroll(jwt(profile="other"), profile="Lumimao")
        cr.http.request = Mock(return_value={"profiles": [
            {"profile_id": "active", "profile_name": "Lumimao"},
            {"profile_id": "other", "profile_name": "Outro"}]})
        with self.assertRaises(s.SyncError):
            cr.verify_profile()

    def test_catalog_chunking_keeps_custom_entries(self):
        al = s.AniList("fake-token", delay=0)
        al.viewer = {"id": 1, "name": "demo"}
        responses = [
            {"MediaListCollection": {"hasNextChunk": True, "lists": [
                {"entries": [entry(10)]}, {"entries": [entry(10), entry(20)]}]}},
            {"MediaListCollection": {"hasNextChunk": False, "lists": [{"entries": [entry(30)]}]}}]
        al.gql = Mock(side_effect=responses)
        self.assertEqual({e["mediaId"] for e in al.collection()}, {10, 20, 30})

    def test_creation_omits_null_id(self):
        al = s.AniList("fake-token", delay=0)
        al.gql = Mock(return_value={"SaveMediaListEntry": {}})
        al.save({"mediaId": 10, "after": {"status": "CURRENT", "progress": 1}}, None)
        query, variables = al.gql.call_args.args
        self.assertNotIn("id:$id", query)
        self.assertNotIn("id", variables)

    def test_updates_include_existing_id_and_same_dates(self):
        al = s.AniList("fake-token", delay=0)
        al.gql = Mock(return_value={"SaveMediaListEntry": {}})
        e = entry(progress=1)
        al.save({"mediaId": 10, "after": {"status": "COMPLETED", "progress": 3}}, e)
        query, variables = al.gql.call_args.args
        self.assertIn("id:$id", query)
        self.assertEqual(variables["id"], e["id"])
        self.assertEqual(variables["start"], e["startedAt"])


class FakeAL:
    def __init__(self, entries, disconnect=False, corrupt=False):
        self.state = {e["mediaId"]: copy.deepcopy(e) for e in entries}
        self.http = Mock()
        self.http.check_cancelled = lambda: None
        self.calls = 0
        self.disconnect = disconnect
        self.corrupt = corrupt

    def identify(self, expected):
        return {"id": 1, "name": "demo"}

    def collection(self):
        return copy.deepcopy(list(self.state.values()))

    def entry(self, media_id):
        return copy.deepcopy(self.state.get(media_id))

    def save(self, change, current):
        self.calls += 1
        e = copy.deepcopy(current) if current else entry(change["mediaId"])
        e.update(change["after"])
        if self.corrupt:
            e["score"] = 0
        self.state[e["mediaId"]] = e
        if self.disconnect:
            self.disconnect = False
            raise s.ApiError("connection lost")
        return copy.deepcopy(e)


class ApplyTests(unittest.TestCase):
    def make_plan(self, e):
        return s.build_plan([group([1, 2, 3])], [e], {10: media()},
                            mapping(), {"id": 1, "name": "demo"})

    def test_round_trip_and_idempotency(self):
        e = entry(progress=1)
        al = FakeAL([e])
        plan = self.make_plan(e)
        with tempfile.TemporaryDirectory() as folder:
            first = s.apply_plan(al, plan, folder)
            second = s.apply_plan(al, plan, folder)
            self.assertTrue(first["success"])
            self.assertEqual(first["applied"], 1)
            self.assertEqual(second["applied"], 0)
            self.assertEqual(al.calls, 1)
            self.assertEqual(s.protected(e), s.protected(al.state[10]))

    def test_changed_score_makes_plan_stale_before_any_write(self):
        e = entry(progress=1)
        plan = self.make_plan(e)
        changed = copy.deepcopy(e)
        changed["score"] = 9
        al = FakeAL([changed])
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(s.SyncError):
            s.apply_plan(al, plan, folder)
        self.assertEqual(al.calls, 0)

    def test_unknown_transport_outcome_verified_without_second_save(self):
        e = entry(progress=1)
        al = FakeAL([e], disconnect=True)
        with tempfile.TemporaryDirectory() as folder:
            result = s.apply_plan(al, self.make_plan(e), folder)
            journal = [json.loads(x) for x in (Path(folder)/"diario-aplicacao.jsonl").read_text().splitlines()]
            self.assertEqual([x["phase"] for x in journal], ["attempt", "confirmed"])
        self.assertEqual(al.calls, 1)
        self.assertTrue(result["success"])

    def test_protected_mismatch_stops_and_records_uncertain_attempt(self):
        e = entry(progress=1)
        al = FakeAL([e], corrupt=True)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(s.SyncError):
                s.apply_plan(al, self.make_plan(e), folder)
            report = s.load_json(Path(folder)/"execucao-interrompida.json")
            self.assertEqual(report["uncertain"], [10])
        self.assertEqual(al.calls, 1)

    def test_offline_plan_cannot_be_written(self):
        e = entry(progress=1)
        plan = self.make_plan(e)
        plan["offline"] = True
        al = FakeAL([e])
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(s.SyncError):
            s.apply_plan(al, plan, folder)
        self.assertEqual(al.calls, 0)


if __name__ == "__main__":
    unittest.main()
