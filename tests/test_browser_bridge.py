import http.client
import json
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import browser_bridge as b
import sync_anilist as s
from test_sync import jwt


def cr_payload():
    return {"service": "cr", "url": "https://www.crunchyroll.com/content/v2/account/watch-history?page_size=100",
            "headers": {"authorization": "Bearer " + jwt(), "sec-fetch-site": "same-origin"}}


def al_payload():
    return {"service": "al", "url": "https://anilist.co/graphql",
            "headers": {"cookie": "fake_session=fake", "x-csrf-token": "fake-csrf"}}


class PayloadTests(unittest.TestCase):
    def test_valid_credentials_are_filtered(self):
        service, value = b.credential_from_payload(cr_payload())
        self.assertEqual(service, "cr")
        _, headers = s.parse_fetch(value, "cr")
        self.assertIn("authorization", headers)
        self.assertNotIn("sec-fetch-site", headers)

    def test_web_anilist_credential(self):
        service, value = b.credential_from_payload(al_payload())
        self.assertEqual(service, "al")
        self.assertIn("fake-csrf", value)

    def test_foreign_and_unexpected_origins_rejected(self):
        for url in ("http://anilist.co/graphql", "https://evil.example/graphql",
                    "https://anilist.co:443/graphql", "https://name@anilist.co/graphql",
                    "https://anilist.co/graphql#fragment"):
            with self.subTest(url=url), self.assertRaises(s.SyncError):
                b.credential_from_payload({**al_payload(), "url": url})

    def test_missing_cookie_rejected(self):
        p = al_payload()
        p["headers"].pop("cookie")
        with self.assertRaises(s.SyncError):
            b.credential_from_payload(p)

    def test_newline_and_non_string_header_rejected(self):
        for value in ("fake\nsecret", 42):
            with self.subTest(value=value), self.assertRaises(s.SyncError):
                b.credential_from_payload({**al_payload(), "headers": {"cookie": value}})


class LocalBridgeTests(unittest.TestCase):
    def setUp(self):
        self.delivered = []
        self.deliveries = threading.Condition()
        def delivered(service, value):
            with self.deliveries:
                self.delivered.append((service, value))
                self.deliveries.notify_all()
        self.bridge = b.LocalBridge(delivered)
        self.url = self.bridge.start()

    def tearDown(self):
        self.bridge.close()

    def request(self, path="/bridge/ping", data=None, auth=True, origin=None, host=None, raw=None):
        headers = {}
        if auth:
            headers["Authorization"] = "Bearer " + self.bridge.key
        if origin:
            headers["Origin"] = origin
        if host:
            headers["Host"] = host
        body = raw if raw is not None else json.dumps(data).encode() if data is not None else None
        if body is not None:
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection("127.0.0.1", self.bridge.port, timeout=3)
        try:
            connection.request("POST" if body is not None else "GET", path, body=body, headers=headers)
            result = connection.getresponse()
            return result.status, result.read().decode("utf-8")
        finally:
            connection.close()

    def test_only_loopback_is_bound_and_secret_is_fragment(self):
        self.assertEqual(self.bridge.server.server_address[0], "127.0.0.1")
        self.assertIn("/conectar#", self.url)
        code, text = self.request("/conectar", auth=False)
        self.assertEqual(code, 200)
        self.assertNotIn(self.bridge.key, text)

    def test_handshake_needs_secret(self):
        code, _ = self.request(auth=False)
        self.assertEqual(code, 403)
        code, text = self.request()
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(text)["protocol"], b.PROTOCOL)

    def test_web_origins_and_rebinding_host_rejected(self):
        for origin in ("https://evil.example", "http://127.0.0.1:1234", "null"):
            with self.subTest(origin=origin):
                self.assertEqual(self.request(origin=origin)[0], 403)
        self.assertEqual(self.request(host="evil.example")[0], 403)

    def test_extension_origin_can_pair(self):
        code, _ = self.request(origin="chrome-extension://" + "a"*32)
        self.assertEqual(code, 200)

    def test_both_services_are_delivered_in_memory(self):
        for p in (al_payload(), cr_payload()):
            self.assertEqual(self.request("/bridge/access", data=p)[0], 200)
        # Aguarda os callbacks, executados depois da resposta HTTP.
        with self.deliveries:
            self.assertTrue(self.deliveries.wait_for(lambda: len(self.delivered) == 2, timeout=1))
        self.assertEqual({service for service, _ in self.delivered}, {"al", "cr"})

    def test_repeated_service_does_not_replace_access(self):
        self.request("/bridge/access", data=al_payload())
        self.request("/bridge/access", data=al_payload())
        with self.deliveries:
            self.assertTrue(self.deliveries.wait_for(lambda: len(self.delivered) == 1, timeout=1))

    def test_expired_and_wrong_secret_are_refused(self):
        self.bridge.deadline = 0
        self.assertEqual(self.request()[0], 403)
        self.assertEqual(self.request("/bridge/access", data=al_payload())[0], 403)
        self.assertEqual(self.delivered, [])

    def test_invalid_json_and_payload_size(self):
        self.assertEqual(self.request("/bridge/access", raw=b"{")[0], 400)
        self.assertEqual(self.request("/bridge/access", raw=b"x"*65537)[0], 413)
        self.assertEqual(self.delivered, [])

    def test_wrong_endpoint_and_absent_auth_do_not_deliver(self):
        self.assertEqual(self.request("/elsewhere", data=al_payload())[0], 403)
        self.assertEqual(self.request("/bridge/access", data=al_payload(), auth=False)[0], 403)
        self.assertEqual(self.delivered, [])

    def test_close_revokes_key_and_is_idempotent(self):
        self.bridge.close()
        self.bridge.close()
        self.assertEqual(self.bridge.key, "")
        self.assertTrue(self.bridge.closed)


if __name__ == "__main__":
    unittest.main()
