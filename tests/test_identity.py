from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sync_anilist as s
from test_sync import jwt


class AutomaticIdentityTests(unittest.TestCase):
    def test_anilist_viewer_identifies_any_authenticated_account_without_name(self):
        al = s.AniList("fake", delay=0)
        al.gql = Mock(return_value={"Viewer": {"id": 42, "name": "OutraConta"}})
        self.assertEqual(al.identify(), {"id": 42, "name": "OutraConta"})
        self.assertEqual(al.viewer["id"], 42)
        self.assertIn("Viewer", al.gql.call_args.args[0])

    def test_anilist_without_viewer_is_not_treated_as_authenticated(self):
        al = s.AniList("fake", delay=0)
        al.gql = Mock(return_value={"Viewer": None})
        with self.assertRaises(s.SyncError):
            al.identify()

    def test_cr_uses_active_token_profile_not_first_profile_or_fixed_name(self):
        cr = s.Crunchyroll(jwt(profile="active"))
        cr.http.request = Mock(return_value={"profiles": [
            {"profile_id": "first", "profile_name": "Lumimao"},
            {"profile_id": "active", "profile_name": "Outro perfil"}]})
        info = cr.verify_profile()
        self.assertEqual(info["profile_id"], "active")
        self.assertEqual(info["verified_name"], "Outro perfil")
        self.assertEqual(info["identity_source"], "profile_api")

    def test_cr_nested_profile_response_is_understood(self):
        cr = s.Crunchyroll(jwt(profile="active"))
        cr.http.request = Mock(return_value={"data": {"profiles": [
            {"id": "active", "name": "Perfil ativo"}]}})
        self.assertEqual(cr.verify_profile()["verified_name"], "Perfil ativo")

    def test_cr_name_lookup_failure_keeps_id_then_validates_history(self):
        cr = s.Crunchyroll(jwt(profile="active"))
        cr.http.log = lambda _: None
        cr.http.request = Mock(side_effect=[s.ApiError("profile lookup refused", 403),
                                            {"data": [], "meta": {}}])
        history = cr.history()
        self.assertEqual(history["profile"]["profile_id"], "active")
        self.assertIsNone(history["profile"]["verified_name"])
        self.assertTrue(history["profile"]["history_verified"])
        self.assertEqual(s.profile_label(history["profile"]), "active")

    def test_cr_missing_active_id_never_guesses_from_profiles(self):
        cr = s.Crunchyroll(jwt(profile=None))
        cr.http.request = Mock(return_value={"profiles": [
            {"profile_id": "first", "profile_name": "First"}]})
        with self.assertRaises(s.SyncError):
            cr.verify_profile()
        cr.http.request.assert_not_called()

    def test_cr_unlisted_active_id_does_not_adopt_another_name(self):
        cr = s.Crunchyroll(jwt(profile="active"))
        cr.http.request = Mock(return_value={"profiles": [
            {"profile_id": "first", "profile_name": "Wrong"}]})
        info = cr.verify_profile()
        self.assertEqual(info["profile_id"], "active")
        self.assertIsNone(info["verified_name"])

    def test_optional_expected_anilist_name_still_rejects_other_account(self):
        al = s.AniList("fake", delay=0)
        al.gql = Mock(return_value={"Viewer": {"id": 42, "name": "OutraConta"}})
        with self.assertRaises(s.SyncError):
            al.identify("Esperada")

    def test_preview_reports_automatic_identity_and_keeps_it_in_plan(self):
        user = {"id": 42, "name": "ContaDetectada"}
        profile = {"profile_id": "active", "verified_name": "Perfil detectado"}
        cr, al = Mock(), Mock()
        cr.history.return_value = {"complete": True, "groups": [], "profile": profile}
        al.identify.return_value = user
        al.collection.return_value = []
        al.catalog.return_value = {}
        callback = Mock()
        with patch.object(s, "write_preview"):
            plan = s.preview_live(cr, al, {"groups": {}}, "unused", on_identity=callback)
        al.identify.assert_called_once_with(None)
        callback.assert_called_once_with(user, profile)
        self.assertEqual(plan["user"], user)
        self.assertEqual(plan["cr_profile"], profile)
        self.assertEqual(plan["changes"], [])

    def test_imported_history_is_not_labeled_as_live_cr_profile(self):
        self.assertEqual(s.profile_label({"identity_source": "imported_history"}),
                         "Historico importado (JSON)")


if __name__ == "__main__":
    unittest.main()
