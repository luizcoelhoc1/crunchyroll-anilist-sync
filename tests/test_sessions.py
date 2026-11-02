"""Sessões fictícias: renovação, isolamento de conta/perfil e armazenamento protegido."""
import copy
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
import urllib.error
from unittest.mock import Mock, call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import browser_login as b
import session_store as s
import sync_anilist as core
from test_sync import jwt


def record(expiry=None):
    return s.cr_record(jwt(expiry=expiry), "cookie-ficticio", b.PUBLIC_CR_CLIENT)


class RenewalTests(unittest.TestCase):
    def test_valid_access_does_not_contact_token_endpoint(self):
        session = s.CrunchyrollSession(record())
        with patch.object(s, "exchange_cr") as exchange:
            self.assertEqual(session.access(), session.record["access_token"])
            exchange.assert_not_called()
        self.assertNotIn("cookie-ficticio", repr(session))

    def test_expired_access_renews_and_persists_rotation(self):
        saved = Mock()
        session = s.CrunchyrollSession(record(time.time() - 10), saved)
        fresh = jwt(expiry=time.time() + 3600)
        with patch.object(s, "exchange_cr", return_value=(fresh, "cookie-rotacionado")) as exchange:
            self.assertEqual(session.access(), fresh)
            self.assertEqual(session.access(), fresh)
        exchange.assert_called_once()
        self.assertEqual(saved.call_args.args[0]["refresh_cookie"], "cookie-rotacionado")
        self.assertEqual(session.record["access_token"], fresh)

    def test_account_token_is_scoped_back_to_saved_profile(self):
        session = s.CrunchyrollSession(record(time.time() - 10))
        with patch.object(s, "exchange_cr", side_effect=[
                (jwt(profile=None), "rotated-1"), (jwt(), "rotated-2")]) as exchange:
            session.access()
        self.assertEqual([c.args[1] for c in exchange.call_args_list],
                         ["etp_rt_cookie", "refresh_token_profile_id"])
        self.assertEqual(exchange.call_args_list[1].args[2], "rotated-1")
        self.assertEqual(session.record["refresh_cookie"], "rotated-2")

    def test_other_profile_is_never_adopted_after_second_grant(self):
        original = record(time.time() - 10)
        saved = Mock()
        session = s.CrunchyrollSession(original, saved)
        with patch.object(s, "exchange_cr", return_value=(jwt(profile="wrong"), "other")):
            with self.assertRaisesRegex(core.SyncError, "outro perfil"):
                session.access()
        self.assertEqual(session.record, original)
        saved.assert_not_called()

    def test_other_account_is_refused_before_profile_grant(self):
        original = record(time.time() - 10)
        session = s.CrunchyrollSession({**original, "account_id": "account"})
        wrong = jwt().replace("header.", "other.")
        claims = core.jwt_claims(wrong)
        claims["scopes"]["cr"]["acc_id"] = "wrong"
        import base64
        wrong = "header." + base64.urlsafe_b64encode(json.dumps(claims).encode()).decode() + ".fake"
        with patch.object(s, "exchange_cr", return_value=(wrong, "other")) as exchange:
            with self.assertRaisesRegex(core.SyncError, "outra conta"):
                session.access()
        self.assertEqual(exchange.call_count, 1)
        self.assertEqual(session.record, original)

    def test_expired_server_response_is_refused(self):
        session = s.CrunchyrollSession(record(time.time() - 10))
        with patch.object(s, "exchange_cr", return_value=(jwt(expiry=time.time() - 20), "cookie")):
            with self.assertRaisesRegex(core.SyncError, "expirado"):
                session.access()

    def test_forced_renewal_refreshes_even_with_valid_access(self):
        session = s.CrunchyrollSession(record())
        with patch.object(s, "exchange_cr", return_value=(jwt(), "cookie")) as exchange:
            session.access(force=True)
        exchange.assert_called_once()

    def test_damaged_identity_and_header_injection_are_refused(self):
        for change in ({"profile_id": "another"}, {"refresh_cookie": "secret\r\nHost: evil"},
                       {"client_authorization": "Bearer wrong"}):
            with self.subTest(change=change), self.assertRaises(core.SyncError):
                s.CrunchyrollSession({**record(), **change})

    def test_core_accepts_managed_session_and_refreshes_expired_token(self):
        session = s.CrunchyrollSession(record(time.time() - 10))
        with patch.object(s, "exchange_cr", return_value=(jwt(), "new-cookie")):
            client = core.Crunchyroll(session)
        self.assertEqual(client.account_id, "account")
        self.assertEqual(client.claims["profile_id"], "active")
        self.assertIn("authorization", client.http.authorize())

    def test_exchange_uses_only_pinned_web_endpoint_and_cookie_grant(self):
        response = Mock()
        response.read.return_value = json.dumps({"access_token": jwt(), "refresh_token": "rotated"}).encode()
        response.headers.get_all.return_value = ["etp_rt=server-cookie; Secure; HttpOnly"]
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.return_value = response
        with patch.object(s.urllib.request, "build_opener", return_value=opener):
            _, cookie = s.exchange_cr(record(), "etp_rt_cookie", "cookie-ficticio")
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://www.crunchyroll.com/auth/v1/token")
        self.assertIn(b"grant_type=etp_rt_cookie", request.data)
        self.assertEqual(request.get_header("Cookie"), "etp_rt=cookie-ficticio")
        self.assertEqual(cookie, "server-cookie")


class AuthRetryTests(unittest.TestCase):
    def client(self):
        authorize = Mock(return_value={"authorization": "Bearer fake"})
        client = core.HttpClient(core.CR_ORIGIN, authorize=authorize)
        return client, authorize

    def response(self):
        response = Mock()
        response.read.return_value = b'{"data": []}'
        response.headers = {}
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        return response

    def unauthorized(self):
        return urllib.error.HTTPError(core.CR_ORIGIN, 401, "unauthorized", {}, BytesIO())

    def test_read_retries_once_after_401(self):
        client, auth = self.client()
        client.opener = Mock()
        client.opener.open.side_effect = [self.unauthorized(), self.response()]
        self.assertEqual(client.request("GET", "/test"), {"data": []})
        self.assertEqual(client.opener.open.call_count, 2)
        self.assertEqual(sum(c.kwargs.get("force", False) for c in auth.call_args_list), 1)

    def test_second_401_stops_without_loop(self):
        client, auth = self.client()
        client.opener = Mock()
        client.opener.open.side_effect = [self.unauthorized(), self.unauthorized()]
        with self.assertRaises(core.ApiError):
            client.request("GET", "/test")
        self.assertEqual(client.opener.open.call_count, 2)

    def test_mutation_is_never_repeated(self):
        client, auth = self.client()
        client.opener = Mock()
        client.opener.open.side_effect = self.unauthorized()
        with self.assertRaises(core.ApiError):
            client.request("POST", "/test", {"query": "fake"}, mutation=True)
        self.assertEqual(client.opener.open.call_count, 1)
        auth.assert_called_once_with()

    def test_403_is_not_misclassified_as_expired_token(self):
        client, auth = self.client()
        client.opener = Mock()
        client.opener.open.side_effect = urllib.error.HTTPError(core.CR_ORIGIN, 403, "denied", {}, BytesIO())
        with self.assertRaises(core.ApiError):
            client.request("GET", "/test")
        auth.assert_called_once_with()


@unittest.skipUnless(os.name == "nt", "DPAPI requer Windows")
class ProtectedStoreTests(unittest.TestCase):
    def test_client_secret_is_protected_and_bound_to_its_client_id(self):
        with tempfile.TemporaryDirectory(prefix="cral-client-test-") as folder:
            path = Path(folder) / "client-credentials.dat"
            store = s.ClientSecretStore(path)
            store.save("55193", "client-secret-ficticio")
            self.assertNotIn(b"client-secret-ficticio", path.read_bytes())
            self.assertEqual(s.ClientSecretStore(path).get("55193"), "client-secret-ficticio")
            self.assertIsNone(store.get("another-client"))
            store.clear()
            self.assertFalse(path.exists())

    def test_real_dpapi_roundtrip_no_plaintext_and_logout_removes_file(self):
        with tempfile.TemporaryDirectory(prefix="cral-test-") as folder:
            path = Path(folder) / "sessions.dat"
            store = s.SessionStore(path)
            store.put("al", {"access_token": "ficticio-token", "expires_at": 9999999999})
            store.put("cr", record())
            raw = path.read_bytes()
            self.assertNotIn(b"ficticio-token", raw)
            self.assertNotIn(b"cookie-ficticio", raw)
            self.assertEqual(s.SessionStore(path).load()["cr"], store.records["cr"])
            self.assertFalse(path.with_suffix(".tmp").exists())
            store.clear()
            self.assertFalse(path.exists())
            self.assertEqual(s.SessionStore(path).load(), {})

    def test_modified_ciphertext_is_refused(self):
        encrypted = bytearray(s.protect(b'{"version":1,"accounts":{}}'))
        encrypted[-1] ^= 0xff
        with self.assertRaises(core.SyncError):
            s.protect(bytes(encrypted), decrypt=True)


class BrowserChoiceTests(unittest.TestCase):
    def test_explicit_edge_does_not_select_chrome(self):
        with tempfile.TemporaryDirectory() as folder:
            executable = Path(folder) / "Microsoft/Edge/Application/msedge.exe"
            executable.parent.mkdir(parents=True)
            executable.touch()
            with patch.dict(b.os.environ, {"PROGRAMFILES(X86)": folder}, clear=True), \
                    patch.object(b, "chrome_path") as chrome:
                self.assertEqual(b.browser_path("edge"), str(executable))
            chrome.assert_not_called()

    def test_missing_edge_reports_error_instead_of_reopening_chrome(self):
        with patch.dict(b.os.environ, {}, clear=True), patch.object(b.shutil, "which", return_value=None), \
                patch.object(b, "chrome_path") as chrome, self.assertRaisesRegex(core.SyncError, "Edge não foi encontrado"):
            b.browser_path("edge")
        chrome.assert_not_called()


class OAuthTests(unittest.TestCase):
    def browser(self, events):
        browser = Mock()
        browser.__enter__ = Mock(return_value=browser)
        browser.__exit__ = Mock(return_value=False)
        browser.events.return_value = iter(events)
        browser.command.return_value = {"cookies": [{
            "name": "etp_rt", "value": "cookie-ficticio", "domain": ".crunchyroll.com"}]}
        return browser

    def history_events(self):
        url = core.CR_ORIGIN + "/content/v2/account/watch-history?page_size=20"
        return [
            {"method": "Network.requestWillBeSent", "params": {"requestId": "history", "request": {
                "url": url, "headers": {"Authorization": "Bearer " + jwt()}}}},
            {"method": "Network.responseReceived", "params": {"requestId": "history", "response": {
                "url": url, "status": 200}}}]

    def test_fresh_browser_starts_at_login_then_opens_history_for_active_profile(self):
        events = [
            {"method": "Page.frameNavigated", "params": {"frame": {
                "id": "main", "url": "https://sso.crunchyroll.com/login"}}},
            {"method": "Page.frameNavigated", "params": {"frame": {
                "id": "main", "url": "https://www.crunchyroll.com/"}}},
            {"method": "Network.requestWillBeSentExtraInfo", "params": {
                "requestId": "profile", "headers": {"Authorization": "Bearer " + jwt()}}},
            {"method": "Network.requestWillBeSent", "params": {"requestId": "profile", "request": {
                "url": core.CR_ORIGIN + "/accounts/v1/me/profile"}}},
            *self.history_events()]
        browser = self.browser(events)
        status = Mock()
        with patch.object(b, "LoginBrowser", return_value=browser):
            result = b.login_crunchyroll(on_status=status)
        self.assertEqual(result["profile_id"], "active")
        self.assertEqual(browser.navigate.call_args_list, [call(b.CR_LOGIN_URL), call(b.CR_HISTORY_URL)])
        self.assertIn("Entre no Crunchyroll", status.call_args_list[0].args[0])

    def test_recaptcha_only_informs_user_without_reloading_login(self):
        captcha = {"method": "Network.requestWillBeSent", "params": {"requestId": "captcha", "request": {
            "url": "https://www.google.com/recaptcha/enterprise/anchor?fake=test"}}}
        browser = self.browser([captcha, captcha, *self.history_events()])
        status = Mock()
        with patch.object(b, "LoginBrowser", return_value=browser):
            result = b.login_crunchyroll(on_status=status)
        self.assertEqual(result["profile_id"], "active")
        self.assertEqual(sum("reCAPTCHA" in c.args[0] for c in status.call_args_list), 1)
        browser.navigate.assert_called_once_with(b.CR_LOGIN_URL)

    def test_edge_retry_uses_isolated_browser_and_same_session_capture(self):
        browser = self.browser(self.history_events())
        with patch.object(b, "LoginBrowser", return_value=browser) as launch:
            result = b.login_crunchyroll(preferred_browser="edge")
        launch.assert_called_once_with(None, preferred_browser="edge")
        browser.navigate.assert_called_once_with(b.CR_LOGIN_URL)
        self.assertEqual(result["refresh_cookie"], "cookie-ficticio")

    def test_anonymous_or_unscoped_tokens_do_not_skip_login_and_profile_selection(self):
        def events():
            yield {"method": "Page.frameNavigated", "params": {"frame": {
                "id": "main", "url": core.CR_ORIGIN + "/"}}}
            for token in ("anonymous", jwt(profile=None)):
                yield {"method": "Network.requestWillBeSent", "params": {"requestId": token, "request": {
                    "url": core.CR_ORIGIN + "/accounts/v1/me/profile", "headers": {"Authorization": "Bearer " + token}}}}
            raise core.Cancelled("cancelled")
        browser = self.browser(events())
        with patch.object(b, "LoginBrowser", return_value=browser), self.assertRaises(core.Cancelled):
            b.login_crunchyroll()
        browser.navigate.assert_called_once_with(b.CR_LOGIN_URL)
        browser.command.assert_not_called()

    def test_login_is_not_interrupted_until_main_page_returns_from_sso(self):
        browser = self.browser([])
        def events():
            yield {"method": "Page.frameNavigated", "params": {"frame": {
                "id": "main", "url": "https://sso.crunchyroll.com/login"}}}
            yield {"method": "Network.requestWillBeSent", "params": {"requestId": "profile", "request": {
                "url": core.CR_ORIGIN + "/accounts/v1/me/profile", "headers": {"Authorization": "Bearer " + jwt()}}}}
            browser.navigate.assert_called_once_with(b.CR_LOGIN_URL)
            yield {"method": "Page.frameNavigated", "params": {"frame": {
                "id": "child", "parentId": "main", "url": core.CR_ORIGIN + "/"}}}
            browser.navigate.assert_called_once_with(b.CR_LOGIN_URL)
            yield {"method": "Page.frameNavigated", "params": {"frame": {
                "id": "main", "url": core.CR_ORIGIN + "/"}}}
            yield from self.history_events()
        browser.events.return_value = events()
        with patch.object(b, "LoginBrowser", return_value=browser):
            b.login_crunchyroll()
        self.assertEqual(browser.navigate.call_args_list, [call(b.CR_LOGIN_URL), call(b.CR_HISTORY_URL)])

    def test_history_401_returns_to_login_once_and_does_not_loop(self):
        url = core.CR_ORIGIN + "/content/v2/account/watch-history"
        denied = {"method": "Network.responseReceived", "params": {
            "requestId": "denied", "response": {"url": url, "status": 401}}}
        browser = self.browser([denied, denied])
        with patch.object(b, "LoginBrowser", return_value=browser), self.assertRaisesRegex(core.SyncError, "não aceitou"):
            b.login_crunchyroll()
        self.assertEqual(browser.navigate.call_args_list, [call(b.CR_LOGIN_URL), call(b.CR_LOGIN_URL)])

    def test_callback_is_not_interrupted_even_after_profile_token_arrives(self):
        browser = self.browser([])
        def events():
            yield {"method": "Page.frameNavigated", "params": {"frame": {
                "id": "main", "url": core.CR_ORIGIN + "/callback?state=%2F"}}}
            yield {"method": "Network.requestWillBeSent", "params": {"requestId": "profile", "request": {
                "url": core.CR_ORIGIN + "/accounts/v1/me/profile", "headers": {"Authorization": "Bearer " + jwt()}}}}
            browser.navigate.assert_called_once_with(b.CR_LOGIN_URL)
            yield {"method": "Page.navigatedWithinDocument", "params": {
                "frameId": "main", "url": core.CR_ORIGIN + "/"}}
            yield from self.history_events()
        browser.events.return_value = events()
        with patch.object(b, "LoginBrowser", return_value=browser):
            b.login_crunchyroll()
        self.assertEqual(browser.navigate.call_args_list, [call(b.CR_LOGIN_URL), call(b.CR_HISTORY_URL)])

    def test_cloudflare_challenge_is_not_treated_as_success_or_reloaded(self):
        events = self.history_events()
        challenge = {"method": "Network.responseReceived", "params": {"requestId": "history", "response": {
            "url": core.CR_ORIGIN + "/content/v2/account/watch-history", "status": 200,
            "headers": {"Cf-Mitigated": "challenge"}}}}
        browser = self.browser([])
        status = Mock()
        def stream():
            yield events[0]
            yield challenge
            yield challenge
            browser.command.assert_not_called()
            browser.navigate.assert_called_once_with(b.CR_LOGIN_URL)
            yield events[1]
        browser.events.return_value = stream()
        with patch.object(b, "LoginBrowser", return_value=browser):
            result = b.login_crunchyroll(on_status=status)
        self.assertEqual(result["profile_id"], "active")
        self.assertEqual(sum("Cloudflare" in c.args[0] for c in status.call_args_list), 1)

    def test_cr_capture_waits_for_success_and_handles_extra_headers_first(self):
        browser = Mock()
        browser.__enter__ = Mock(return_value=browser)
        browser.__exit__ = Mock(return_value=False)
        url = core.CR_ORIGIN + "/content/v2/account/watch-history?page_size=20"
        browser.events.return_value = iter([
            {"method": "Network.requestWillBeSentExtraInfo", "params": {"requestId": "1", "headers": {
                "Authorization": "Bearer " + jwt(), "User-Agent": "FakeBrowser"}}},
            {"method": "Network.requestWillBeSent", "params": {"requestId": "1", "request": {"url": url}}},
            {"method": "Network.responseReceived", "params": {"requestId": "1", "response": {"url": url, "status": 200}}}])
        browser.command.return_value = {"cookies": [{"name": "etp_rt", "value": "cookie-ficticio", "domain": ".crunchyroll.com"}]}
        with patch.object(b, "LoginBrowser", return_value=browser):
            result = b.login_crunchyroll()
        self.assertEqual(result["profile_id"], "active")
        self.assertEqual(result["user_agent"], "FakeBrowser")
        self.assertEqual(result["refresh_cookie"], "cookie-ficticio")
        self.assertEqual(browser.command.call_args.args[0], "Network.getCookies")
        browser.navigate.assert_called_once_with(b.CR_LOGIN_URL)

    def test_current_profile_mode_does_not_start_isolated_browser(self):
        browser = self.browser(self.history_events())
        with patch("chrome_profile.CurrentChrome", return_value=browser) as current, \
                patch.object(b, "LoginBrowser") as isolated:
            result = b.login_crunchyroll(use_existing=True)
        current.assert_called_once()
        isolated.assert_not_called()
        self.assertEqual(result["profile_id"], "active")

    def test_existing_extension_cookie_can_bootstrap_managed_session(self):
        value = "fetch(" + json.dumps(core.CR_ORIGIN + "/content/v2/account/watch-history") + "," + json.dumps({
            "headers": {"authorization": "Bearer " + jwt(),
                        "cookie": "other=discard; etp_rt=cookie-ficticio; device_id=existing-device"}}) + ")"
        with patch.object(s, "exchange_cr") as exchange:
            result = b.cr_record_from_fetch(value)
        self.assertEqual(result["refresh_cookie"], "cookie-ficticio")
        self.assertEqual(result["device_id"], "existing-device")
        self.assertNotIn("other", result)
        exchange.assert_not_called()

    def test_extension_without_refresh_cookie_keeps_legacy_access(self):
        value = "fetch(" + json.dumps(core.CR_ORIGIN + "/content/v2/account/watch-history") + "," + json.dumps({
            "headers": {"authorization": "Bearer " + jwt(), "cookie": "other=discard"}}) + ")"
        self.assertIsNone(b.cr_record_from_fetch(value))


if __name__ == "__main__":
    unittest.main()
