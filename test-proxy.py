#!/usr/bin/env python3
"""Unit + HTTP tests for shared Kimi key resolution. Never calls Moonshot."""

from __future__ import annotations

import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import proxy as P


MINI_PLAN = {
    "title": "toy",
    "qubits": 1,
    "gates": [{"op": "H", "q": 0}],
    "explain_th": "a\nb\nc\nd",
    "explain_en": "a\nb\nc\nd",
    "mapping": "joke",
    "is_toy": True,
}

SECRET = "sk-SERVER-SECRET-do-not-leak-9f3a"
VISITOR = "sk-VISITOR-own-key-aaaa"


def _clear_env() -> None:
    for name in ("MOONSHOT_API_KEY", "KIMI_API_KEY"):
        os.environ.pop(name, None)


class ResolveKeyTests(unittest.TestCase):
    def setUp(self) -> None:
        _clear_env()

    def tearDown(self) -> None:
        _clear_env()

    def test_visitor_wins_over_env(self) -> None:
        os.environ["MOONSHOT_API_KEY"] = SECRET
        key, src = P.resolve_moonshot_key("  " + VISITOR + "  ")
        self.assertEqual(key, VISITOR)
        self.assertEqual(src, "visitor")

    def test_env_used_when_settings_blank(self) -> None:
        os.environ["MOONSHOT_API_KEY"] = SECRET
        key, src = P.resolve_moonshot_key("")
        self.assertEqual(key, SECRET)
        self.assertEqual(src, "server")
        key2, src2 = P.resolve_moonshot_key(None)
        self.assertEqual(key2, SECRET)
        self.assertEqual(src2, "server")

    def test_kimi_api_key_alias(self) -> None:
        os.environ["KIMI_API_KEY"] = SECRET
        key, src = P.resolve_moonshot_key("   ")
        self.assertEqual(key, SECRET)
        self.assertEqual(src, "server")

    def test_moonshot_env_preferred_over_kimi_alias(self) -> None:
        os.environ["MOONSHOT_API_KEY"] = SECRET
        os.environ["KIMI_API_KEY"] = "sk-ALIAS-should-not-win"
        key, src = P.resolve_moonshot_key("")
        self.assertEqual(key, SECRET)
        self.assertEqual(src, "server")

    def test_neither_key(self) -> None:
        key, src = P.resolve_moonshot_key("")
        self.assertEqual(key, "")
        self.assertEqual(src, "")


class RateLimitTests(unittest.TestCase):
    def setUp(self) -> None:
        P.reset_plan_rate_limit()

    def tearDown(self) -> None:
        P.reset_plan_rate_limit()

    def test_allows_then_blocks(self) -> None:
        ip = "203.0.113.9"
        for i in range(P.PLAN_RATE_MAX):
            self.assertTrue(P.plan_rate_ok(ip), "hit %d should pass" % i)
        self.assertFalse(P.plan_rate_ok(ip))
        self.assertTrue(P.plan_rate_ok("203.0.113.10"))


class HttpProxyTests(unittest.TestCase):
    def setUp(self) -> None:
        _clear_env()
        P.reset_plan_rate_limit()
        self.captured: dict = {}
        self._orig_plan = P.plan_from_kimi

        def fake_plan(prompt, endpoint, model, key):
            self.captured["key"] = key
            self.captured["model"] = model
            self.captured["prompt"] = prompt
            self.captured["endpoint"] = endpoint
            return {"ok": True, "plan": MINI_PLAN}

        P.plan_from_kimi = fake_plan
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), P.Handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        P.plan_from_kimi = self._orig_plan
        _clear_env()
        P.reset_plan_rate_limit()

    def _url(self, path: str) -> str:
        return "http://127.0.0.1:%d%s" % (self.port, path)

    def _post(self, path: str, obj: dict, headers: dict | None = None) -> tuple[int, dict]:
        data = json.dumps(obj).encode("utf-8")
        hdrs = {"Content-Type": "application/json"}
        if headers:
            hdrs.update(headers)
        req = Request(self._url(path), data=data, headers=hdrs, method="POST")
        try:
            with urlopen(req, timeout=5) as resp:
                raw = resp.read().decode("utf-8")
                return resp.status, json.loads(raw)
        except HTTPError as e:
            raw = e.read().decode("utf-8")
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                body = {"raw": raw}
            return e.code, body

    def _get(self, path: str) -> tuple[int, dict]:
        req = Request(self._url(path), method="GET")
        with urlopen(req, timeout=5) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw)

    def test_blank_body_uses_env_and_does_not_leak(self) -> None:
        os.environ["MOONSHOT_API_KEY"] = SECRET
        code, body = self._post("/plan", {"prompt": "dog or cat toy", "moonshot_key": ""})
        self.assertEqual(code, 200, body)
        self.assertEqual(self.captured.get("key"), SECRET)
        self.assertEqual(self.captured.get("model"), P.DEFAULT_MODEL)
        blob = json.dumps(body)
        self.assertNotIn(SECRET, blob)
        self.assertEqual(body.get("qubits"), 1)

    def test_visitor_key_preferred_in_http(self) -> None:
        os.environ["MOONSHOT_API_KEY"] = SECRET
        code, body = self._post(
            "/plan",
            {"prompt": "bell toy", "moonshot_key": VISITOR, "model": "kimi-k3"},
        )
        self.assertEqual(code, 200, body)
        self.assertEqual(self.captured.get("key"), VISITOR)
        self.assertNotIn(SECRET, json.dumps(body))
        self.assertNotIn(VISITOR, json.dumps(body))

    def test_shared_key_locks_model(self) -> None:
        os.environ["KIMI_API_KEY"] = SECRET
        code, body = self._post(
            "/plan",
            {"prompt": "hadamard", "moonshot_key": "", "model": "expensive-other-model"},
        )
        self.assertEqual(code, 200, body)
        self.assertEqual(self.captured.get("model"), "kimi-k3")

    def test_missing_key_is_400(self) -> None:
        code, body = self._post("/plan", {"prompt": "hello", "moonshot_key": ""})
        self.assertEqual(code, 400)
        self.assertIn("key", str(body.get("error", "")).lower())
        self.assertNotIn(SECRET, json.dumps(body))

    def test_health_boolean_only(self) -> None:
        os.environ["MOONSHOT_API_KEY"] = SECRET
        code, body = self._get("/health")
        self.assertEqual(code, 200)
        self.assertTrue(body.get("ok"))
        self.assertTrue(body.get("proxy"))
        self.assertTrue(body.get("kimi_shared"))
        blob = json.dumps(body)
        self.assertNotIn(SECRET, blob)
        self.assertNotIn("MOONSHOT_API_KEY", blob)
        self.assertNotIn("KIMI_API_KEY", blob)

    def test_health_false_without_env(self) -> None:
        code, body = self._get("/health")
        self.assertEqual(code, 200)
        self.assertFalse(body.get("kimi_shared"))

    def test_blank_prompt_does_not_burn_rate(self) -> None:
        os.environ["MOONSHOT_API_KEY"] = SECRET
        hdrs = {"X-Forwarded-For": "198.51.100.40"}
        for _ in range(P.PLAN_RATE_MAX + 2):
            code, body = self._post("/plan", {"prompt": "  ", "moonshot_key": ""}, headers=hdrs)
            self.assertEqual(code, 400, body)
        code, body = self._post("/plan", {"prompt": "toy", "moonshot_key": ""}, headers=hdrs)
        self.assertEqual(code, 200, body)

    def test_rate_limit_http(self) -> None:
        os.environ["MOONSHOT_API_KEY"] = SECRET
        hdrs = {"X-Forwarded-For": "198.51.100.7"}
        last = 0
        last_body: dict = {}
        for _ in range(P.PLAN_RATE_MAX + 1):
            last, last_body = self._post(
                "/plan",
                {"prompt": "toy", "moonshot_key": ""},
                headers=hdrs,
            )
        self.assertEqual(last, 429, last_body)
        self.assertNotIn(SECRET, json.dumps(last_body))

    def test_leftmost_xff_does_not_bypass(self) -> None:
        os.environ["MOONSHOT_API_KEY"] = SECRET
        right = "198.51.100.7"
        last = 0
        for i in range(P.PLAN_RATE_MAX + 1):
            last, body = self._post(
                "/plan",
                {"prompt": "toy", "moonshot_key": ""},
                headers={"X-Forwarded-For": "203.0.113.%d, %s" % (i, right)},
            )
        self.assertEqual(last, 429, body)

    def test_global_cap_ignores_fresh_ips(self) -> None:
        os.environ["MOONSHOT_API_KEY"] = SECRET
        old = P.PLAN_RATE_GLOBAL_MAX
        P.PLAN_RATE_GLOBAL_MAX = 3
        P.reset_plan_rate_limit()
        try:
            codes = []
            for i in range(4):
                code, body = self._post(
                    "/plan",
                    {"prompt": "toy", "moonshot_key": ""},
                    headers={"X-Forwarded-For": "203.0.113.%d" % (i + 20)},
                )
                codes.append(code)
                self.assertNotIn(SECRET, json.dumps(body))
            self.assertEqual(codes[:3], [200, 200, 200])
            self.assertEqual(codes[3], 429)
        finally:
            P.PLAN_RATE_GLOBAL_MAX = old
            P.reset_plan_rate_limit()

    def test_private_files_are_not_served(self) -> None:
        for path in ("/proxy.py", "/Dockerfile", "/proof/", "/proof/dogcat.json", "/test-proxy.py", "/.env"):
            code, _body, headers = self._get_raw(path)
            self.assertEqual(code, 404, path)
            self.assertNotIn("sk-", _body)
            self.assertEqual(headers.get("X-Frame-Options"), "DENY")
            self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")

    def test_public_assets_and_health_headers(self) -> None:
        code, body, headers = self._get_raw("/")
        self.assertEqual(code, 200)
        self.assertIn("ทดลองควอนตัม", body)
        self.assertEqual(headers.get("X-Frame-Options"), "DENY")
        self.assertIn("frame-ancestors", headers.get("Content-Security-Policy", ""))
        code_js, js, _ = self._get_raw("/app.js")
        self.assertEqual(code_js, 200)
        self.assertIn("function", js)
        status, health = self._get("/health")
        self.assertEqual(status, 200)
        self.assertIn("kimi_shared", health)

    def _get_raw(self, path: str) -> tuple[int, str, dict]:
        req = Request(self._url(path), method="GET")
        try:
            with urlopen(req, timeout=5) as resp:
                return resp.status, resp.read().decode("utf-8", "replace"), dict(resp.headers)
        except HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace"), dict(e.headers)


class OriginGuardTests(unittest.TestCase):
    def tearDown(self) -> None:
        P.ORIGIN_JOBS.clear()

    def test_other_key_cannot_read_cached_job(self) -> None:
        jid = "job-audit-1"
        P._store_origin_job(
            jid,
            {
                "task": object(),
                "n": 1,
                "device": "WK_C180",
                "shots": 256,
                "key_fp": P._key_fp("owner-key-12345678"),
            },
        )
        out = P.origin_job("intruder-key-87654321", jid, 1)
        blob = json.dumps(out)
        self.assertFalse(out.get("ok"))
        self.assertNotIn("counts", out)
        self.assertNotIn("raw", out)
        self.assertNotIn("owner-key", blob)
        self.assertNotIn("intruder-key", blob)

    def test_scrub_strips_secret(self) -> None:
        secret = "sk-SECRET-value-aaaa"
        out = P.scrub_result({"raw": "leak " + secret + " end", "ok": False}, secret)
        self.assertNotIn(secret, json.dumps(out))
        self.assertIn("***", out["raw"])

    def test_qasm_too_long_never_calls_sdk(self) -> None:
        out = P.origin_sample("visitor-key-12345678", "x" * (P.MAX_QASM + 1), "WK_C180", 256, 1)
        self.assertFalse(out.get("ok"))
        self.assertIn("too long", out.get("error", ""))

    def test_job_cache_is_capped(self) -> None:
        for i in range(P.ORIGIN_JOB_CAP + 5):
            P._store_origin_job("j%d" % i, {"key_fp": "x"})
        self.assertLessEqual(len(P.ORIGIN_JOBS), P.ORIGIN_JOB_CAP)
        self.assertIn("j%d" % (P.ORIGIN_JOB_CAP + 4), P.ORIGIN_JOBS)
        self.assertNotIn("j0", P.ORIGIN_JOBS)


class RedirectTests(unittest.TestCase):
    def test_moonshot_redirect_does_not_forward_bearer(self) -> None:
        hit = {"auth": None, "n": 0}

        class Evil(BaseHTTPRequestHandler):
            def do_POST(self):
                hit["n"] += 1
                hit["auth"] = self.headers.get("Authorization")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"choices":[{"message":{"content":"{}"}}]}')

            def log_message(self, fmt, *args):
                return

        class Bounce(BaseHTTPRequestHandler):
            evil_url = ""

            def do_POST(self):
                self.send_response(302)
                self.send_header("Location", Bounce.evil_url)
                self.end_headers()

            def log_message(self, fmt, *args):
                return

        evil = ThreadingHTTPServer(("127.0.0.1", 0), Evil)
        evil_thread = threading.Thread(target=evil.serve_forever, daemon=True)
        evil_thread.start()
        Bounce.evil_url = "http://127.0.0.1:%d/steal" % evil.server_address[1]
        bounce = ThreadingHTTPServer(("127.0.0.1", 0), Bounce)
        bounce_thread = threading.Thread(target=bounce.serve_forever, daemon=True)
        bounce_thread.start()
        try:
            endpoint = "http://127.0.0.1:%d/v1/chat/completions" % bounce.server_address[1]
            result = P.moonshot_chat("toy", endpoint, "kimi-k3", SECRET)
            self.assertFalse(result.get("ok"))
            self.assertEqual(hit["n"], 0)
            self.assertIsNone(hit["auth"])
            self.assertNotIn(SECRET, json.dumps(result))
        finally:
            bounce.shutdown()
            evil.shutdown()
            bounce.server_close()
            evil.server_close()


if __name__ == "__main__":
    unittest.main()
