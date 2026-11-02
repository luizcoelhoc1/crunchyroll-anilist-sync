"""Broker OAuth com retorno HTTP local real e credenciais fictícias."""
from io import BytesIO
import base64
import hashlib
import json
from pathlib import Path
import sys
import unittest
import urllib.error
from urllib.parse import parse_qs, urlencode, urlsplit
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import oauth_service as service
from sync_anilist import ApiError, Cancelled, SyncError
from test_oauth_callback import available_redirect, request

ORIGIN = "https://auth.example.workers.dev"


class ServiceLoginTests(unittest.TestCase):
    def test_public_login_requires_proof_and_never_sends_client_secret(self):
        redirect = available_redirect()
        calls = []

        def exchange(origin, path, body):
            calls.append((origin, path, body))
            if path == "/v1/session":
                return {"client_id": "55193", "session": "signed.session"}
            return {"access_token": "fake-user-token", "expires_in": 3600, "token_type": "Bearer"}

        def browser(url):
            target = urlsplit(url)
            self.assertEqual(target.scheme + "://" + target.netloc + target.path,
                             "https://anilist.co/api/v2/oauth/authorize")
            values = parse_qs(target.query)
            self.assertEqual(values["state"], ["signed.session"])
            self.assertEqual(values["redirect_uri"], [ORIGIN + "/v1/callback"])
            local_state = calls[0][2]["state"]
            self.assertEqual(request(redirect + "?" + urlencode({"state": local_state, "code": "fake-code"}))[0], 200)

        with patch.object(service, "service_request", side_effect=exchange), \
                patch.object(service, "open_regular_browser", side_effect=browser):
            result = service.login_via_service("55193", ORIGIN, redirect_uri=redirect)
        self.assertEqual(result["access_token"], "fake-user-token")
        self.assertEqual([call[1] for call in calls], ["/v1/session", "/v1/token"])
        proof = calls[1][2]["code_verifier"]
        challenge = base64.urlsafe_b64encode(hashlib.sha256(proof.encode()).digest()).decode().rstrip("=")
        self.assertEqual(challenge, calls[0][2]["code_challenge"])
        self.assertNotIn(proof, json.dumps(calls[0]))
        self.assertNotIn("client_secret", json.dumps(calls))
        with self.assertRaises(OSError):
            request(redirect)

    def test_cancel_before_session_does_not_contact_service_or_open_browser(self):
        with patch.object(service, "service_request") as remote, patch.object(service, "open_regular_browser") as browser:
            with self.assertRaises(Cancelled):
                service.login_via_service("55193", ORIGIN, lambda: True)
        remote.assert_not_called()
        browser.assert_not_called()

    def test_invalid_session_or_wrong_client_is_rejected_before_browser(self):
        for data in ({"session": "bad", "client_id": "55193"},
                     {"session": "signed.session", "client_id": "other"}):
            with patch.object(service, "service_request", return_value=data), \
                    patch.object(service, "open_regular_browser") as browser:
                with self.assertRaises(SyncError):
                    service.login_via_service("55193", ORIGIN, redirect_uri=available_redirect())
            browser.assert_not_called()

    def test_service_url_requires_an_https_origin_without_credentials_query_or_path(self):
        self.assertEqual(service.service_url(ORIGIN + "/"), ORIGIN)
        for url in ("http://auth.example", "https://user:secret@auth.example", "https://auth.example/token",
                    "https://auth.example?secret=x", "https://127.0.0.1", "https://auth.example:444"):
            with self.subTest(url=url), self.assertRaises(SyncError):
                service.service_url(url)

    def test_http_and_redirect_errors_never_echo_server_responses_or_retry(self):
        for status in (400, 403, 429, 500):
            opener = Mock()
            opener.open.side_effect = urllib.error.HTTPError(ORIGIN, status, "denied", {}, BytesIO(b"private-code secret"))
            with patch.object(service.urllib.request, "build_opener", return_value=opener):
                with self.assertRaises(SyncError) as caught:
                    service.service_request(ORIGIN, "/v1/token", {"code": "private-code"})
            self.assertNotIn("private-code", str(caught.exception))
            self.assertNotIn("secret", str(caught.exception))
            self.assertEqual(opener.open.call_count, 1)
        opener.open.side_effect = ApiError("redirect", 302)
        with patch.object(service.urllib.request, "build_opener", return_value=opener):
            with self.assertRaisesRegex(SyncError, "Redirecionamento"):
                service.service_request(ORIGIN, "/v1/session", {})


if __name__ == "__main__":
    unittest.main()
