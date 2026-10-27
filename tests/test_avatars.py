import email.message
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import avatars
import sync_anilist as s
from test_sync import jwt


class AvatarTests(unittest.TestCase):
    def test_anilist_medium_avatar_is_used(self):
        url = "https://s4.anilist.co/file/anilistcdn/user/avatar/medium/example.jpg"
        self.assertEqual(avatars.avatar_url("al", {"avatar": {"medium": url}}), url)

    def test_cr_avatar_filename_is_scoped_to_static_cdn(self):
        self.assertEqual(avatars.avatar_url("cr", {"avatar": "hime.png"}),
                         "https://static.crunchyroll.com/assets/avatar/170x170/hime.png")
        self.assertIsNone(avatars.avatar_url("cr", {"avatar": "../../private.png"}))

    def test_unexpected_hosts_and_credentials_are_refused(self):
        for url in ("http://s4.anilist.co/a.png", "https://evil.example/a.png",
                    "https://s4.anilist.co.evil.example/a.png",
                    "https://user:pass@s4.anilist.co/a.png"):
            self.assertFalse(avatars.allowed_avatar_url(url, "al"))

    def test_download_sends_no_session_headers(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.headers = email.message.Message()
        response.headers["Content-Type"] = "image/png"
        response.read.return_value = b"fake-png"
        opener = Mock()
        opener.open.return_value = response
        with patch.object(avatars.urllib.request, "build_opener", return_value=opener):
            data = avatars.download_avatar("https://s4.anilist.co/a.png", "al")
        self.assertEqual(data, b"fake-png")
        headers = {k.lower(): v for k, v in opener.open.call_args.args[0].header_items()}
        self.assertNotIn("authorization", headers)
        self.assertNotIn("cookie", headers)

    def test_large_avatar_and_html_are_refused(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.headers = email.message.Message()
        response.headers["Content-Type"] = "text/html"
        opener = Mock()
        opener.open.return_value = response
        with patch.object(avatars.urllib.request, "build_opener", return_value=opener):
            with self.assertRaises(ValueError):
                avatars.download_avatar("https://s4.anilist.co/a.png", "al")
            response.headers.replace_header("Content-Type", "image/png")
            response.read.return_value = b"x" * (avatars.MAX_BYTES + 1)
            with self.assertRaises(ValueError):
                avatars.download_avatar("https://s4.anilist.co/a.png", "al")

    def test_redirect_cannot_leave_service_hosts(self):
        with self.assertRaises(ValueError):
            avatars.AvatarRedirect("al").redirect_request(None, None, 302, "", {},
                                                         "https://evil.example/a.png")

    def test_profile_metadata_keeps_avatar_of_active_profile(self):
        cr = s.Crunchyroll(jwt())
        cr.http.request = Mock(return_value={"profiles": [
            {"profile_id": "other", "profile_name": "Wrong", "avatar": "wrong.png"},
            {"profile_id": "active", "profile_name": "Right", "avatar": "right.png"}]})
        info = cr.identify()
        self.assertEqual(info["avatar"], "right.png")
        self.assertTrue(info["session_verified"])

    def test_token_only_identity_requires_server_validation(self):
        cr = s.Crunchyroll(jwt())
        cr.http.request = Mock(side_effect=[s.ApiError("name refused", 403),
                                            s.ApiError("invalid session", 401)])
        with self.assertRaises(s.ApiError):
            cr.identify()


if __name__ == "__main__":
    unittest.main()
