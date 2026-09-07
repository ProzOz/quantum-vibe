#!/usr/bin/env python3
"""Unit + HTTP tests for shared Kimi key resolution. Never calls Moonshot."""

from __future__ import annotations

import json
import os
import threading
import unittest
from http.server import ThreadingHTTPServer
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


if __name__ == "__main__":
    unittest.main()
