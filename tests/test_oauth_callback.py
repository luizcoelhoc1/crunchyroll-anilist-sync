"""Código OAuth por HTTP real em loopback, sem autenticar contas reais."""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
from pathlib import Path
import socket
import sys
import threading
import time
import unittest
import urllib.error
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlencode, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import oauth_login as o
from sync_anilist import ApiError, Cancelled, SyncError


def available_redirect():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    return f"http://127.0.0.1:{port}/anilist/callback"


def request(uri, *, host=None, method="GET"):
    target = urlsplit(uri)
    connection = http.client.HTTPConnection("127.0.0.1", target.port, timeout=3)
    headers = {"Host": host} if host else {}
    path = target.path + ("?" + target.query if target.query else "")
    try:
        connection.request(method, path, headers=headers)
        response = connection.getresponse()
        return response.status, response.read(), dict(response.getheaders())
    finally:
        connection.close()


class CallbackTests(unittest.TestCase):
    def setUp(self):
        self.callback = o.OAuthCallback(available_redirect())
        self.callback.__enter__()

    def tearDown(self):
        self.callback.__exit__()

    def callback_uri(self, **change):
        return self.callback.redirect_uri + "?" + urlencode({
            "state": self.callback.state, "code": "codigo-ficticio", **change})

    def test_callback_page_has_no_credentials_and_restricts_scripts(self):
        status, body, headers = request(self.callback.redirect_uri)
        self.assertEqual(status, 200)
        self.assertNotIn(self.callback.state.encode(), body)
        self.assertNotIn(b"codigo-ficticio", body)
        self.assertIn("script-src 'sha256-", headers["Content-Security-Policy"])
        self.assertIn(b"history.replaceState", body)
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_code_is_received_without_manual_copy_or_reflection(self):
        status, body, _ = request(self.callback_uri())
        self.assertEqual(status, 200)
        self.assertEqual(self.callback.wait(), "codigo-ficticio")
        self.assertNotIn(b"codigo-ficticio", body)
        self.assertNotIn(self.callback.state.encode(), body)
        self.assertIn("ainda precisa validar".encode(), body)

    def test_wrong_state_does_not_cancel_legitimate_login(self):
        self.assertEqual(request(self.callback_uri(state="wrong"))[0], 403)
        self.assertFalse(self.callback.done.is_set())
        self.assertEqual(request(self.callback_uri())[0], 200)

    def test_rebinding_host_and_wrong_path_are_refused(self):
        self.assertEqual(request(self.callback_uri(), host="evil.example")[0], 403)
        self.assertEqual(request(self.callback.redirect_uri + "/other")[0], 403)
        self.assertFalse(self.callback.done.is_set())

    def test_duplicate_does_not_replace_first_code(self):
        self.assertEqual(request(self.callback_uri())[0], 200)
        self.assertEqual(request(self.callback_uri(code="second"))[0], 409)
        self.assertEqual(self.callback.wait(), "codigo-ficticio")

    def test_denial_reaches_application_as_error(self):
        self.assertEqual(request(self.callback_uri(error="access_denied"))[0], 400)
        with self.assertRaisesRegex(SyncError, "recusada"):
            self.callback.wait()

    def test_missing_code_and_duplicate_parameters_are_rejected(self):
        uris = [self.callback_uri(code=""), self.callback_uri() + "&code=second",
                self.callback_uri() + "&state=second",
                self.callback.redirect_uri + "?code=missing-state"]
        for uri in uris:
            with self.subTest(uri=uri):
                self.assertIn(request(uri)[0], (400, 403))
        self.assertFalse(self.callback.done.is_set())

    def test_old_fragment_post_is_no_longer_accepted(self):
        self.assertEqual(request(self.callback.redirect_uri, method="POST")[0], 405)
        self.assertFalse(self.callback.done.is_set())

    def test_cancellation_and_expiration_stop_waiting(self):
        with self.assertRaises(Cancelled):
            self.callback.wait(lambda: True)
        self.callback.deadline = 0
        with self.assertRaisesRegex(SyncError, "prazo"):
            self.callback.wait()

    def test_busy_port_is_reported_without_opening_browser(self):
        with self.assertRaisesRegex(SyncError, "ocupada"):
            o.OAuthCallback(self.callback.redirect_uri)


class RegularBrowserLoginTests(unittest.TestCase):
    def test_login_requests_code_then_exchanges_it_without_exposing_secret_in_url(self):
        redirect_uri = available_redirect()
        result = {"access_token": "fake-oauth", "expires_at": time.time() + 3600}

        def simulate_consent(url):
            params = parse_qs(urlsplit(url).query)
            self.assertEqual(params["client_id"], ["55193"])
            self.assertEqual(params["redirect_uri"], [redirect_uri])
            self.assertEqual(params["response_type"], ["code"])
            self.assertNotIn("secret-ficticio", url)
            uri = redirect_uri + "?" + urlencode({"state": params["state"][0], "code": "fake-code"})
            self.assertEqual(request(uri)[0], 200)

        with patch.object(o, "open_regular_browser", side_effect=simulate_consent) as browser, \
                patch.object(o, "exchange_code", return_value=result) as exchange:
            actual = o.login_anilist("55193", redirect_uri, client_secret="secret-ficticio")
        browser.assert_called_once()
        exchange.assert_called_once_with("55193", "secret-ficticio", "fake-code", redirect_uri)
        self.assertEqual(actual, result)
        with self.assertRaises(OSError):
            request(redirect_uri)

    def test_missing_secret_stops_before_opening_browser(self):
        with patch.object(o, "open_regular_browser") as browser:
            with self.assertRaisesRegex(SyncError, "Client Secret"):
                o.login_anilist("55193", available_redirect())
        browser.assert_not_called()

    def test_cancelled_login_does_not_open_browser(self):
        with patch.object(o, "open_regular_browser") as browser:
            with self.assertRaises(Cancelled):
                o.login_anilist("55193", available_redirect(), lambda: True, client_secret="fake-secret")
        browser.assert_not_called()

    def test_regular_browser_uses_chrome_launcher_without_isolated_profile(self):
        url = "https://anilist.co/api/v2/oauth/authorize?client_id=55193&response_type=code"
        with patch.object(o, "open_chrome") as chrome:
            o.open_regular_browser(url)
        chrome.assert_called_once_with(url)

    def test_foreign_callback_and_pin_configuration_are_refused(self):
        for uri in ("https://evil.example/anilist/callback", "https://anilist.co/api/v2/oauth/pin",
                    "http://localhost:8765/anilist/callback", "http://127.0.0.1:8765/wrong"):
            with self.subTest(uri=uri), self.assertRaises(SyncError):
                o.OAuthCallback(uri)


class CodeExchangeTests(unittest.TestCase):
    def test_real_http_exchange_works_when_server_rejects_default_python_user_agent(self):
        seen = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                agent = self.headers.get("User-Agent", "")
                seen.append(agent)
                rejected = not agent or agent.startswith("Python-urllib/")
                body = json.dumps({"error": "forbidden"} if rejected else {
                    "access_token": "fake-token", "expires_in": 3600, "token_type": "Bearer"}).encode()
                self.send_response(403 if rejected else 200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
        thread.start()
        try:
            endpoint = f"http://127.0.0.1:{server.server_address[1]}/token"
            with patch.object(o, "TOKEN_ENDPOINT", endpoint):
                result = o.exchange_code("55193", "fake-secret", "fake-code", o.REDIRECT_URI)
            self.assertEqual(result["access_token"], "fake-token")
            self.assertEqual(len(seen), 1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def response(self, data):
        response = Mock()
        response.read.return_value = json.dumps(data).encode()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        return response

    def test_exchange_sends_documented_grant_in_json_to_pinned_token_endpoint(self):
        opener = Mock()
        opener.open.return_value = self.response({"access_token": "fake-token", "token_type": "Bearer", "expires_in": 3600})
        with patch.object(o.urllib.request, "build_opener", return_value=opener) as builder:
            result = o.exchange_code("55193", "fake-secret", "fake-code", o.REDIRECT_URI)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, o.TOKEN_ENDPOINT)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(json.loads(request.data), {
            "grant_type": "authorization_code", "client_id": "55193",
            "client_secret": "fake-secret", "code": "fake-code", "redirect_uri": o.REDIRECT_URI})
        self.assertEqual(result["access_token"], "fake-token")
        self.assertGreater(result["expires_at"], time.time() + 3500)
        self.assertIsInstance(builder.call_args.args[0], o.PinnedRedirect)

    def test_provider_error_bodies_never_leak_secrets_or_codes(self):
        for error in ("invalid_client", "invalid_grant", "unsupported_grant_type"):
            opener = Mock()
            raw = json.dumps({"error": error, "message": "fake-secret fake-code"}).encode()
            opener.open.side_effect = urllib.error.HTTPError(o.TOKEN_ENDPOINT, 400, "failed", {}, BytesIO(raw))
            with self.subTest(error=error), patch.object(o.urllib.request, "build_opener", return_value=opener):
                with self.assertRaises(SyncError) as caught:
                    o.exchange_code("55193", "fake-secret", "fake-code", o.REDIRECT_URI)
                self.assertNotIn("fake-secret", str(caught.exception))
                self.assertNotIn("fake-code", str(caught.exception))

    def test_redirect_is_refused_without_retrying_or_forwarding_secret(self):
        opener = Mock()
        opener.open.side_effect = ApiError("redirect", 302)
        with patch.object(o.urllib.request, "build_opener", return_value=opener):
            with self.assertRaisesRegex(SyncError, "Redirecionamento"):
                o.exchange_code("55193", "fake-secret", "fake-code", o.REDIRECT_URI)
        self.assertEqual(opener.open.call_count, 1)

    def test_invalid_token_or_expiry_is_refused(self):
        for data in ([], {}, {"access_token": "bad\r\nheader"}, {"access_token": "fake", "expires_in": 0},
                     {"access_token": "fake", "expires_in": "bad"}):
            with self.subTest(data=data), self.assertRaises(SyncError):
                o.token_response(data)


if __name__ == "__main__":
    unittest.main()
