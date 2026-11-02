"""Protocolo de login direto com contas fictícias; nenhum acesso externo."""
from io import BytesIO
import json
from pathlib import Path
import sys
import time
import unittest
import urllib.error
import urllib.parse
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cr_direct_login as d
import session_store as s
from sync_anilist import ApiError, Cancelled, Crunchyroll, PinnedRedirect, SyncError
from test_sync import jwt


def response(profile="active", refresh="refresh-ficticio"):
    return {"access_token": jwt(profile=profile), "refresh_token": refresh,
            "token_type": "Bearer", "account_id": "account"}


def record(expiry=None):
    return {"auth_method": "password", "access_token": jwt(expiry=expiry),
            "refresh_token": "refresh-ficticio", "account_id": "account", "profile_id": "active",
            "client_authorization": "Basic ficticio", "device_id": "device-ficticio",
            "device_type": "ANDROIDTV", "user_agent": d.USER_AGENT}


def client_with_responses(*data):
    client = d.DirectClient()
    client.request = Mock(side_effect=data)
    return client


class DirectLoginTests(unittest.TestCase):
    def test_password_then_profiles_without_persisting_password(self):
        client = client_with_responses(response(), {"profiles": [
            {"profile_id": "active", "profile_name": "Meu perfil", "can_switch": True}]})
        with patch.object(d, "DirectClient", return_value=client):
            pending = d.login_with_password(" test@example.invalid ", " password with spaces ")
        self.assertEqual(client.request.call_args_list[0].args[0], d.TOKEN_PATH)
        # O dicionário da senha é limpo após a requisição, inclusive em falhas.
        self.assertEqual(client.request.call_args_list[0].args[1], {})
        self.assertEqual(pending.profiles[0]["name"], "Meu perfil")
        self.assertNotIn("password with spaces", repr(pending.__dict__))
        result = pending.select("active")
        self.assertNotIn("password", result)
        self.assertEqual(result["refresh_token"], "refresh-ficticio")
        self.assertEqual(client.request.call_count, 2)
        pending.clear()
        self.assertEqual(pending.record, {})
        self.assertEqual(pending.profiles, [])

    def test_selection_uses_rotated_token_and_checks_selected_profile(self):
        client = client_with_responses(response(profile=None), {"profiles": [
            {"profile_id": "chosen", "profile_name": "Escolhido"}]}, response("chosen", "rotated"))
        with patch.object(d, "DirectClient", return_value=client):
            pending = d.login_with_password("test@example.invalid", "fake-password")
        result = pending.select("chosen")
        self.assertEqual(result["profile_id"], "chosen")
        self.assertEqual(result["refresh_token"], "rotated")
        self.assertEqual(client.request.call_args.args[1], {
            "grant_type": "refresh_token_profile_id", "profile_id": "chosen", "refresh_token": "refresh-ficticio"})

    def test_unknown_or_locked_profile_is_not_requested(self):
        client = client_with_responses()
        pending = d.PendingLogin(client, record(), [{"id": "locked", "name": "Bloqueado", "can_switch": False}])
        for pid in ("unknown", "locked"):
            with self.subTest(pid=pid), self.assertRaises(SyncError):
                pending.select(pid)
        client.request.assert_not_called()

    def test_wrong_selected_profile_is_refused(self):
        client = client_with_responses(response("different"))
        pending = d.PendingLogin(client, record(), [{"id": "chosen", "name": "Escolhido", "can_switch": True}])
        with self.assertRaisesRegex(SyncError, "perfil escolhido"):
            pending.select("chosen")

    def test_bad_tokens_and_profiles_are_refused(self):
        for invalid in ({}, {**response(), "account_id": "wrong"}, {**response(), "refresh_token": "bad\n"},
                        {**response(), "access_token": jwt(expiry=time.time() - 100)},
                        {**response(), "token_type": "mac"}):
            with self.subTest(invalid=invalid), self.assertRaises(SyncError):
                d.token_result(invalid)
        for profiles in ([], [{"profile_id": "../../wrong"}], [{"profile_id": "a"}, {"profile_id": "a"}]):
            client = client_with_responses(response(), {"profiles": profiles})
            with patch.object(d, "DirectClient", return_value=client), self.assertRaises(SyncError):
                d.login_with_password("test@example.invalid", "fake")

    def test_password_request_is_encoded_once_and_confined_to_official_endpoint(self):
        client = d.DirectClient(record())
        captured = []
        reply = Mock()
        reply.headers = {}
        reply.read.return_value = json.dumps(response()).encode()
        reply.__enter__ = Mock(return_value=reply)
        reply.__exit__ = Mock(return_value=False)
        def send(req, timeout):
            captured.append((req.full_url, dict(req.header_items()), urllib.parse.parse_qs(req.data.decode()), req))
            return reply
        client.opener = Mock()
        client.opener.open.side_effect = send
        client.request(d.TOKEN_PATH, {"grant_type": "password", "username": "test@example.invalid", "password": " a&=+ç "})
        url, headers, form, req = captured[0]
        self.assertEqual(url, d.ORIGIN + d.TOKEN_PATH)
        self.assertEqual(form["password"], [" a&=+ç "])
        self.assertEqual(form["device_id"], ["device-ficticio"])
        self.assertEqual(form["device_type"], ["ANDROIDTV"])
        self.assertEqual(headers["Etp-anonymous-id"], "device-ficticio")
        self.assertNotIn("Cookie", headers)
        self.assertIsNone(req.data)
        client.opener.open.assert_called_once()
        with self.assertRaises(SyncError):
            client.request("https://example.invalid/steal")

    def test_redirects_are_disabled(self):
        client = d.DirectClient()
        handler = next(h for h in client.opener.handlers if isinstance(h, PinnedRedirect))
        with self.assertRaises(ApiError):
            handler.redirect_request(None, None, 307, "redirect", {}, "https://example.invalid/")

    def test_login_errors_are_sanitized_without_retry(self):
        for status, error, expected in ((401, "invalid_client", "cliente"), (400, "unsupported_grant_type", "cliente"),
                                        (401, "invalid_grant", "e-mail"), (403, "", "bloqueou"), (429, "", "Muitas")):
            with self.subTest(status=status, error=error):
                client = d.DirectClient()
                client.opener = Mock()
                client.opener.open.side_effect = urllib.error.HTTPError(d.ORIGIN, status, "private",
                    {}, BytesIO(json.dumps({"error": error, "message": "secret-password"}).encode()))
                with self.assertRaisesRegex(ApiError, expected) as caught:
                    client.request(d.TOKEN_PATH, {"grant_type": "password", "password": "secret-password"})
                self.assertNotIn("secret-password", str(caught.exception))
                client.opener.open.assert_called_once()

    def test_cancellation_before_and_after_network_does_not_return_login(self):
        client = d.DirectClient(cancelled=lambda: True)
        client.opener = Mock()
        with self.assertRaises(Cancelled):
            client.request(d.TOKEN_PATH, {"grant_type": "password"})
        client.opener.open.assert_not_called()
        client.cancelled = Mock(side_effect=[False, True])
        reply = Mock()
        reply.headers = {}
        reply.read.return_value = json.dumps(response()).encode()
        reply.__enter__ = Mock(return_value=reply)
        reply.__exit__ = Mock(return_value=False)
        client.opener.open.return_value = reply
        with self.assertRaises(Cancelled):
            client.request(d.TOKEN_PATH, {"grant_type": "password"})


class DirectRenewalTests(unittest.TestCase):
    def test_refresh_uses_same_device_and_rotates_both_grants_before_saving(self):
        saved = Mock()
        original = record(time.time() - 1)
        session = s.CrunchyrollSession(original, saved)
        client = client_with_responses(response(None, "rotation-1"), response("active", "rotation-2"))
        with patch.object(d, "DirectClient", return_value=client) as build, patch.object(s, "exchange_cr") as cookie:
            session.access()
        build.assert_called_once()
        for key in ("device_id", "device_type", "client_authorization", "user_agent"):
            self.assertEqual(build.call_args.args[0][key], original[key])
        cookie.assert_not_called()
        self.assertEqual(client.request.call_args_list[0].args[1]["grant_type"], "refresh_token")
        self.assertEqual(client.request.call_args_list[1].args[1]["refresh_token"], "rotation-1")
        self.assertEqual(session.record["refresh_token"], "rotation-2")
        self.assertNotIn("refresh_cookie", session.record)
        saved.assert_called_once_with(session.record)

    def test_wrong_account_or_profile_does_not_overwrite_saved_session(self):
        for wrong_account in (False, True):
            original = record(time.time() - 1)
            candidate = jwt(profile="wrong")
            if wrong_account:
                import base64
                claims = d.jwt_claims(candidate)
                claims["scopes"]["cr"]["acc_id"] = "other"
                candidate = "header." + base64.urlsafe_b64encode(json.dumps(claims).encode()).decode() + ".fake"
            saved = Mock()
            session = s.CrunchyrollSession(original, saved)
            with patch.object(d, "refresh_session", return_value=(candidate, "rotated")), self.assertRaises(SyncError):
                session.access()
            self.assertEqual(session.record, original)
            saved.assert_not_called()

    def test_restored_direct_session_preserves_platform_user_agent(self):
        session = s.CrunchyrollSession(record())
        client = Crunchyroll(session)
        self.assertEqual(client.http.headers["user-agent"], d.USER_AGENT)
        self.assertNotIn("refresh-ficticio", repr(session))

    def test_real_browser_user_agent_with_semicolons_is_also_valid(self):
        agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        session = s.CrunchyrollSession(s.cr_record(jwt(), "fake-cookie", "Basic fake", agent))
        self.assertEqual(session.record["user_agent"], agent)

    def test_header_injection_is_still_refused(self):
        for key in ("user_agent", "client_authorization", "device_id", "device_type", "refresh_token"):
            for invalid in ("bad\r\nX-Test: injected", "bad\x00value", "", None):
                with self.subTest(key=key, invalid=invalid), self.assertRaises(SyncError):
                    s.CrunchyrollSession({**record(), key: invalid})
        with self.assertRaises(SyncError):
            s.CrunchyrollSession(s.cr_record(jwt(), "fake; injected=value", "Basic fake"))
