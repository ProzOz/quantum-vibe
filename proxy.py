#!/usr/bin/env python3
# ทดลองควอนตัม.com proxy. Visitors paste their own API keys in Settings.
# Never logs keys or request bodies. Origin routes need qpanda3-runtime.
"""ทดลองควอนตัม.com planner proxy (stdlib only)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get("PORT", "3000"))
HOST = os.environ.get("HOST", "0.0.0.0")
DEFAULT_MODEL = "kimi-k3"
DEFAULT_BASE = "https://api.moonshot.ai"
ALLOWED_HOSTS = frozenset(("api.moonshot.ai", "api.moonshot.cn"))
MAX_GATES = 20
MAX_PROMPT = 4000
ALLOWED_OPS = frozenset(
    ("H", "X", "Y", "Z", "S", "T", "CX", "CZ", "SWAP", "RX", "RY", "RZ")
)
ONEQ = frozenset(("H", "X", "Y", "Z", "S", "T"))
TWOQ = frozenset(("CX", "CZ", "SWAP"))
ROT = frozenset(("RX", "RY", "RZ"))

SYSTEM_PROMPT = (
    "You design tiny teaching circuits. Map the user's idea onto at most 4 qubits. "
    "JSON only. Never claim quantum advantage. Never claim the circuit solves a real "
    "problem. Never emit more than 4 qubits or unknown gates. "
    "Voice: blunt friend. Thai or English matching the user prompt (fill both "
    "explain_th and explain_en; the matching one is required). Slang, roast, "
    "slightly dirty jokes OK. Forbidden: porn, slurs. "
    "explain_th and explain_en MUST be exactly four short newline-separated lines: "
    "1) What this toy is pretending to be. "
    "2) What each qubit stands for, one short human line. "
    "3) What the bars actually mean after 1024 local shots. "
    "4) MUST say it is a joke mapping / teaching sketch, not science and not a real model. "
    "mapping: one-line joke of what was reduced. is_toy always true."
)

SCHEMA_HINT = (
    " Return one JSON object with keys: "
    'title (string), qubits (integer 1-4), gates (array, max 20), '
    "explain_th (string, 4 lines), explain_en (string, 4 lines), "
    "mapping (string), is_toy (true). "
    "Allowed ops: H X Y Z S T CX CZ SWAP RX RY RZ. "
    "One-qubit: {op, q}. CX/CZ/SWAP: {op, q, t} with q!=t. "
    "RX/RY/RZ: {op, q, theta} with finite theta. q and t are qubit indices."
)



DEFAULT_DEVICE_ORIGIN = "WK_C180"
DEFAULT_SHOTS_ORIGIN = 256
ORIGIN_CONSOLE_JOB = "https://console.originqc.com.cn/en/jobs/"
# Process-local QTaskManager cache. Poll uses try_get_result (single query).
# Never stores the raw Origin key. Lost on proxy restart.
ORIGIN_JOBS: dict[str, dict] = {}
ORIGIN_JOBS_LOCK = threading.Lock()
POLL_QUERY_TIMEOUT_S = 8


def qpanda_present() -> bool:
    try:
        import qpanda3_runtime  # noqa: F401
        import pyqpanda3  # noqa: F401
        return True
    except Exception:
        return False


def _as_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    return str(v)


def sanitize_error(err: Any, key: str) -> str:
    msg = _as_str(err)
    k = (key or "").strip()
    if k and k in msg:
        msg = msg.replace(k, "***")
    if len(msg) > 800:
        msg = msg[:800] + "…"
    return msg or "Origin error"


def _device_entry(dev: Any) -> dict:
    chip_id = None
    name = None
    try:
        chip_id = dev.chip_id()
    except Exception:
        chip_id = None
    try:
        name = dev.name()
    except Exception:
        name = None
    shown = _as_str(chip_id or name or "?")
    return {"id": shown, "name": _as_str(name or chip_id or shown)}


def origin_test(key: str) -> dict:
    """Login and list devices. No submit."""
    k = (key or "").strip()
    if not k:
        return {"ok": False, "error": "Origin API key is empty"}
    if not qpanda_present():
        return {
            "ok": False,
            "error": "qpanda3-runtime is not installed in this Python. pip install qpanda3-runtime pyqpanda3",
        }
    try:
        from qpanda3_runtime import RuntimeService
    except Exception as e:
        return {"ok": False, "error": "qpanda3-runtime import failed: %s" % sanitize_error(e, k)}
    try:
        svc = RuntimeService()
        svc.login(k)
        devices = svc.list_devices()
    except Exception as e:
        return {"ok": False, "error": sanitize_error(e, k)}
    out = []
    if devices is None:
        devices = []
    if not isinstance(devices, (list, tuple)):
        devices = [devices]
    for d in devices:
        try:
            out.append(_device_entry(d))
        except Exception:
            continue
    ids = [x.get("id") for x in out if x.get("id")]
    return {
        "ok": True,
        "connected": True,
        "devices": out,
        "device_ids": ids,
    }


def _looks_bitstring(k: Any) -> bool:
    s = _as_str(k).strip().replace(" ", "")
    return s != "" and all(c in "01" for c in s)


def _as_finite_float(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        x = float(v)
        if x == x and x not in (float("inf"), float("-inf")):
            return x
        return None
    if isinstance(v, str) and v.strip() != "":
        try:
            x = float(v.strip())
        except ValueError:
            return None
        if x == x and x not in (float("inf"), float("-inf")):
            return x
    return None


def _to_bitstring(label: Any, width: int) -> str | None:
    s = _as_str(label).strip().replace(" ", "")
    for ch in ("|", "⟩", ">", "⟨", "<"):
        s = s.replace(ch, "")
    if not s:
        return None
    bits = None
    low = s.lower()
    if low.startswith("0x"):
        try:
            bits = bin(int(s, 16))[2:]
        except Exception:
            return None
    elif all(c in "01" for c in s):
        bits = s
    else:
        try:
            n = int(s, 10)
        except Exception:
            return None
        if n < 0:
            return None
        bits = bin(n)[2:]
    w = max(1, int(width) if width else 2)
    if len(bits) < w:
        bits = bits.zfill(w)
    elif len(bits) > w:
        bits = bits[-w:]
    return bits


def _looks_label(k: Any) -> bool:
    s = _as_str(k).strip().replace(" ", "")
    if not s:
        return False
    if all(c in "01" for c in s):
        return True
    low = s.lower()
    if low.startswith("0x"):
        try:
            int(s, 16)
            return True
        except Exception:
            return False
    try:
        n = int(s, 10)
        return n >= 0
    except Exception:
        return False


def _as_seq(v: Any) -> list | None:
    if isinstance(v, (list, tuple)):
        return list(v)
    if isinstance(v, str) or v is None:
        return None
    try:
        return list(v)
    except Exception:
        return None


def _pairs_from_key_value(keys: Any, vals: Any, width: int) -> list[tuple[str, float]] | None:
    ks = _as_seq(keys)
    vs = _as_seq(vals)
    if ks is None or vs is None or len(ks) != len(vs) or not ks:
        return None
    out: list[tuple[str, float]] = []
    for k, v in zip(ks, vs):
        bits = _to_bitstring(k, width)
        num = _as_finite_float(v)
        if bits is None or num is None:
            continue
        out.append((bits, num))
    return out or None


def _pairs_from_labeled_dict(obj: dict, width: int) -> list[tuple[str, float]] | None:
    if not obj:
        return None
    keys = list(obj.keys())
    if not keys or not all(_looks_label(k) for k in keys):
        return None
    out: list[tuple[str, float]] = []
    for k, v in obj.items():
        bits = _to_bitstring(k, width)
        num = _as_finite_float(v)
        if bits is None or num is None:
            continue
        out.append((bits, num))
    return out or None


def _parse_preview_string(s: str) -> Any:
    t = (s or "").strip()
    if not t:
        return None
    try:
        return json.loads(t)
    except Exception:
        pass
    start = t.find("{")
    end = t.rfind("}")
    if start >= 0 and end > start:
        chunk = t[start : end + 1]
        for cand in (chunk, chunk.replace("'", '"')):
            try:
                return json.loads(cand)
            except Exception:
                pass
    km = re.search(r"\bkey\s*[:=]\s*(\[[^\[\]]*\])", t, re.I)
    vm = re.search(r"\bvalue\s*[:=]\s*(\[[^\[\]]*\])", t, re.I)
    if km and vm:
        try:
            keys = json.loads(km.group(1).replace("'", '"'))
            vals = json.loads(vm.group(1).replace("'", '"'))
            return {"key": keys, "value": vals}
        except Exception:
            pass
    return None


def _walk_pairs(obj: Any, width: int, depth: int = 0) -> list[tuple[str, float]] | None:
    if depth > 8 or obj is None:
        return None
    if isinstance(obj, str):
        if obj.startswith("Status:"):
            return None
        parsed = _parse_preview_string(obj)
        if parsed is not None and parsed is not obj:
            return _walk_pairs(parsed, width, depth + 1)
        return None
    if isinstance(obj, dict):
        got = _pairs_from_key_value(obj.get("key"), obj.get("value"), width)
        if got:
            return got
        if "counts" in obj:
            got = _walk_pairs(obj.get("counts"), width, depth + 1)
            if got:
                return got
        labeled = _pairs_from_labeled_dict(obj, width)
        if labeled:
            return labeled
        for nest in ("results", "data", "result"):
            if nest in obj:
                got = _walk_pairs(obj.get(nest), width, depth + 1)
                if got:
                    return got
        for v in obj.values():
            got = _walk_pairs(v, width, depth + 1)
            if got:
                return got
        return None
    if isinstance(obj, (list, tuple)):
        if obj and all(isinstance(x, dict) and "key" in x and "value" in x for x in obj):
            if all(not isinstance(x.get("key"), (list, tuple)) for x in obj):
                got = _pairs_from_key_value(
                    [x.get("key") for x in obj],
                    [x.get("value") for x in obj],
                    width,
                )
                if got:
                    return got
        for item in obj:
            got = _walk_pairs(item, width, depth + 1)
            if got:
                return got
        return None
    if hasattr(obj, "key") and hasattr(obj, "value") and not isinstance(obj, (bytes, int, float)):
        try:
            got = _pairs_from_key_value(getattr(obj, "key"), getattr(obj, "value"), width)
            if got:
                return got
        except Exception:
            pass
    if hasattr(obj, "counts") and not isinstance(obj, (str, bytes, int, float)):
        try:
            got = _walk_pairs(getattr(obj, "counts"), width, depth + 1)
            if got:
                return got
        except Exception:
            pass
    for name in ("to_dict", "dict", "as_dict"):
        if hasattr(obj, name) and callable(getattr(obj, name)):
            try:
                got = _walk_pairs(getattr(obj, name)(), width, depth + 1)
                if got:
                    return got
            except Exception:
                pass
    return None


def _finalize_origin(results: Any, n: int, shots: int | None = None) -> dict | None:
    try:
        width = int(n)
    except Exception:
        width = 2
    if width < 1:
        width = 2
    try:
        sh = int(shots) if shots is not None else DEFAULT_SHOTS_ORIGIN
    except Exception:
        sh = DEFAULT_SHOTS_ORIGIN
    if sh < 1:
        sh = DEFAULT_SHOTS_ORIGIN
    pairs = _walk_pairs(results, width)
    if not pairs:
        return None
    merged: dict[str, float] = {}
    for bits, val in pairs:
        merged[bits] = merged.get(bits, 0.0) + val
    if not merged:
        return None
    vals = list(merged.values())
    all_probish = all(v <= 1.01 for v in vals)
    total = sum(vals)
    percents: dict[str, float] = {}
    counts: dict[str, int] = {}
    if all_probish and abs(total - 1.0) <= 0.08:
        for k, v in merged.items():
            percents[k] = v * 100.0
            counts[k] = int(round(v * sh))
        return {"counts": counts, "percents": percents, "shots": sh, "n": width}
    for k, v in merged.items():
        counts[k] = int(round(v))
    shot_sum = sum(counts.values())
    if shot_sum <= 0:
        return None
    for k, c in counts.items():
        percents[k] = (c / shot_sum) * 100.0
    return {"counts": counts, "percents": percents, "shots": shot_sum, "n": width}


def extract_counts(results: Any, n: int, shots: int | None = None) -> dict | None:
    parsed = _finalize_origin(results, n, shots)
    if not parsed:
        return None
    return parsed["counts"]


def _qasm_to_prog(qasm: str):
    from pyqpanda3.intermediate_compiler import convert_qasm_string_to_qprog

    text = qasm or ""
    try:
        return convert_qasm_string_to_qprog(text)
    except Exception as first:
        stripped = "\n".join(
            ln for ln in text.splitlines() if "qelib1.inc" not in ln.lower()
        )
        if stripped.strip() != text.strip():
            try:
                return convert_qasm_string_to_qprog(stripped)
            except Exception:
                pass
        raise first


def _result_preview(results: Any) -> str:
    try:
        s = json.dumps(results, ensure_ascii=False, default=str)
    except Exception:
        s = _as_str(type(results).__name__)
    if len(s) > 240:
        s = s[:240] + "…"
    return s


def _to_jsonish(obj: Any, depth: int = 0) -> Any:
    if depth > 6:
        return _as_str(type(obj).__name__)
    if obj is None or isinstance(obj, bool):
        return obj
    if isinstance(obj, int) and not isinstance(obj, bool):
        return obj
    if isinstance(obj, float):
        if obj == obj and obj not in (float("inf"), float("-inf")):
            return obj
        return None
    if isinstance(obj, str):
        return obj if len(obj) <= 8000 else obj[:8000] + "…"
    if isinstance(obj, dict):
        out = {}
        for k, v in list(obj.items())[:120]:
            out[_as_str(k)] = _to_jsonish(v, depth + 1)
        return out
    if isinstance(obj, (list, tuple)):
        return [_to_jsonish(x, depth + 1) for x in list(obj)[:400]]
    if hasattr(obj, "key") and hasattr(obj, "value") and not isinstance(obj, (bytes, int, float)):
        try:
            return {
                "key": _to_jsonish(getattr(obj, "key"), depth + 1),
                "value": _to_jsonish(getattr(obj, "value"), depth + 1),
            }
        except Exception:
            pass
    for name in ("to_dict", "dict", "as_dict"):
        if hasattr(obj, name) and callable(getattr(obj, name)):
            try:
                return _to_jsonish(getattr(obj, name)(), depth + 1)
            except Exception:
                pass
    d = getattr(obj, "__dict__", None)
    if isinstance(d, dict) and d:
        cleaned = {k: v for k, v in d.items() if not str(k).startswith("_")}
        if cleaned:
            return _to_jsonish(cleaned, depth + 1)
    try:
        return list(obj)  # numpy-ish
    except Exception:
        pass
    return _as_str(obj)[:2000]


def _sanitize_raw(results: Any) -> Any:
    """JSON-serializable Origin preview. Does not include API keys."""
    try:
        obj = _to_jsonish(results)
        json.dumps(obj, ensure_ascii=False)
        return obj
    except Exception:
        return _result_preview(results)


def _key_fp(key: str) -> str:
    return hashlib.sha256((key or "").encode("utf-8")).hexdigest()[:16]


def _console_url(job_id: str) -> str:
    return ORIGIN_CONSOLE_JOB + _as_str(job_id).strip()


def _task_status_token(obj: Any, depth: int = 0) -> str:
    if depth > 8 or obj is None:
        return ""
    if isinstance(obj, str):
        s = obj.strip()
        low = s.lower()
        for prefix in ("task status:", "status:"):
            if low.startswith(prefix):
                return s.split(":", 1)[-1].strip().lower()
        if low in ("received", "queuing", "running", "processing", "failed", "canceled", "finished"):
            return low
        return ""
    if isinstance(obj, dict):
        for v in obj.values():
            got = _task_status_token(v, depth + 1)
            if got:
                return got
        return ""
    if isinstance(obj, (list, tuple)):
        for item in obj:
            got = _task_status_token(item, depth + 1)
            if got:
                return got
        return ""
    return ""


def _looks_timeout(msg: str) -> bool:
    low = (msg or "").lower()
    return (
        "timeout" in low
        or "timed out" in low
        or "time out" in low
        or "took more than" in low
    )


def origin_sample(key: str, qasm: str, device_id: str, shots: int, n_qubits: int) -> dict:
    """Submit OpenQASM to Wukong and return job_id immediately. Never wait for chip result."""
    k = (key or "").strip()
    if not k:
        return {"ok": False, "error": "Origin API key is empty"}
    if not qpanda_present():
        return {
            "ok": False,
            "error": "qpanda3-runtime is not installed in this Python. pip install qpanda3-runtime pyqpanda3",
        }
    qasm = _as_str(qasm).strip()
    if not qasm:
        return {"ok": False, "error": "OpenQASM is empty"}
    device_id = (_as_str(device_id).strip() or DEFAULT_DEVICE_ORIGIN)
    try:
        shots_n = int(shots)
    except Exception:
        shots_n = DEFAULT_SHOTS_ORIGIN
    if shots_n != DEFAULT_SHOTS_ORIGIN:
        shots_n = DEFAULT_SHOTS_ORIGIN
    try:
        n = int(n_qubits)
    except Exception:
        n = 0
    if n < 1 or n > 4:
        return {"ok": False, "error": "qubits must be 1–4"}
    try:
        from qpanda3_runtime import RuntimeService
    except Exception as e:
        return {"ok": False, "error": "qpanda3-runtime import failed: %s" % sanitize_error(e, k)}
    try:
        prog = _qasm_to_prog(qasm)
    except Exception as e:
        return {"ok": False, "error": "OpenQASM convert failed: %s" % sanitize_error(e, k)}
    try:
        svc = RuntimeService()
        svc.login(k)
        device = svc.device(device_id)
        measure_qubits = list(range(n))
        task = svc.sample(
            prog,
            device,
            measure_qubits=measure_qubits,
            shots=shots_n,
            is_amend=True,
            is_mapping=True,
            is_optimization=True,
            task_describe="quantum-vibe-local",
        )
    except Exception as e:
        return {"ok": False, "error": sanitize_error(e, k)}
    job_id = ""
    try:
        tid = task.id()
        if isinstance(tid, list):
            tid = tid[0] if tid else ""
        job_id = _as_str(tid).strip()
    except Exception as e:
        return {"ok": False, "error": "Origin sample returned no job id: %s" % sanitize_error(e, k)}
    if not job_id:
        return {"ok": False, "error": "Origin sample returned no job id"}
    with ORIGIN_JOBS_LOCK:
        ORIGIN_JOBS[job_id] = {
            "task": task,
            "n": n,
            "device": device_id,
            "shots": shots_n,
            "key_fp": _key_fp(k),
        }
    return {
        "ok": True,
        "job_id": job_id,
        "status": "submitted",
        "device": device_id,
        "shots": shots_n,
        "n": n,
        "real_qpu": True,
    }



def _attach_existing_origin_job(key: str, job_id: str, n_qubits: Any) -> dict:
    """Reconstruct an existing Origin task by id. Never calls sample / never submits."""
    k = (key or "").strip()
    jid = _as_str(job_id).strip()
    try:
        n = int(n_qubits)
    except Exception:
        n = 2
    if n < 1 or n > 4:
        n = 2
    if not qpanda_present():
        return {
            "ok": False,
            "error": (
                "qpanda3-runtime is not installed in this Python. "
                "Cannot query existing job %s. Console: %s"
                % (jid, _console_url(jid))
            ),
        }
    try:
        from qpanda3_runtime import RuntimeService
    except Exception as e:
        return {
            "ok": False,
            "error": "qpanda3-runtime import failed: %s" % sanitize_error(e, k),
        }
    try:
        svc = RuntimeService()
        svc.login(k)
        # Attach existing task by id. NEVER svc.sample().
        # SDK: RuntimeService.get_task(task_id)
        # Source: C:\Users\Admin\AppData\Local\Programs\Python\Python313\Lib\site-packages\qpanda3_runtime\runtime_service.py
        if not hasattr(svc, "get_task"):
            return {
                "ok": False,
                "error": (
                    "Could not attach Origin job %s by id (SDK has no get_task). "
                    "Console: %s" % (jid, _console_url(jid))
                ),
            }
        task = svc.get_task(jid)
    except Exception as e:
        return {
            "ok": False,
            "error": (
                "Could not attach Origin job %s by id: %s. Console: %s"
                % (jid, sanitize_error(e, k), _console_url(jid))
            ),
        }
    rec = {
        "task": task,
        "n": n,
        "device": DEFAULT_DEVICE_ORIGIN,
        "shots": DEFAULT_SHOTS_ORIGIN,
        "key_fp": _key_fp(k),
    }
    with ORIGIN_JOBS_LOCK:
        ORIGIN_JOBS[jid] = rec
    return {"ok": True, "rec": rec}


def origin_job(key: str, job_id: Any, n_qubits: Any) -> dict:
    """Non-blocking poll. Uses QTaskManager.try_get_result (single query)."""
    k = (key or "").strip()
    if not k:
        return {"ok": False, "error": "Origin API key is empty"}
    jid = _as_str(job_id).strip()
    if not jid:
        return {"ok": False, "error": "job_id is empty"}
    with ORIGIN_JOBS_LOCK:
        rec = ORIGIN_JOBS.get(jid)
    if rec is None:
        attached = _attach_existing_origin_job(k, jid, n_qubits)
        if not attached.get("ok"):
            out = {
                "ok": False,
                "error": attached.get("error") or (
                    "Could not attach Origin job %s by id. Console: %s"
                    % (jid, _console_url(jid))
                ),
                "job_id": jid,
                "console_url": _console_url(jid),
            }
            if attached.get("raw") is not None:
                out["raw"] = attached["raw"]
            return out
        rec = attached["rec"]
    n = rec.get("n")
    try:
        n = int(n) if n is not None else int(n_qubits)
    except Exception:
        n = 0
    if n < 1 or n > 4:
        n = rec.get("n") or 0
        try:
            n = int(n)
        except Exception:
            n = 1
    task = rec["task"]
    try:
        # try_get_result is one HTTP query (single_query=True), not wait-until-done.
        # Source: C:\Users\Admin\AppData\Local\Programs\Python\Python313\Lib\site-packages\qpanda3_runtime\task\qtask_manager.py
        if hasattr(task, "try_get_result"):
            results, finished, _progress = task.try_get_result(timeout=POLL_QUERY_TIMEOUT_S)
        else:
            results = task.get_result_sync(timeout=1)
            finished = True
    except Exception as e:
        msg = sanitize_error(e, k)
        if _looks_timeout(msg):
            return {
                "ok": True,
                "running": True,
                "job_id": jid,
                "status": "running",
            }
        return {"ok": False, "error": msg}
    status = _task_status_token(results) or ("finished" if finished else "running")
    if status in ("failed", "canceled"):
        return {
            "ok": False,
            "error": sanitize_error(
                "Origin job %s %s" % (jid, status),
                k,
            ),
            "raw": _sanitize_raw(results),
            "job_id": jid,
        }
    if (not finished) or status in ("received", "queuing", "running", "processing"):
        return {
            "ok": True,
            "running": True,
            "job_id": jid,
            "status": status if status else "running",
        }
    raw = _sanitize_raw(results)
    shots_n = rec.get("shots") or DEFAULT_SHOTS_ORIGIN
    parsed = _finalize_origin(results, n, shots_n)
    if not parsed:
        return {
            "ok": False,
            "error": "Origin returned no parseable counts",
            "raw": raw,
            "job_id": jid,
        }
    return {
        "ok": True,
        "running": False,
        "job_id": jid,
        "counts": parsed["counts"],
        "percents": parsed["percents"],
        "shots": parsed.get("shots") or shots_n,
        "device": rec.get("device") or DEFAULT_DEVICE_ORIGIN,
        "n": n,
        "noisy": True,
        "real_qpu": True,
        "raw": raw,
    }


def key_present() -> bool:
    """Check if owner env key is present. Not used for visitor keys."""
    return bool(os.environ.get("MOONSHOT_API_KEY"))


def _get_key() -> str:
    """Get owner env key. Not used for visitor keys."""
    return os.environ.get("MOONSHOT_API_KEY") or ""


def as_string(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    return str(v)


def is_int(n: Any) -> bool:
    return isinstance(n, int) and not isinstance(n, bool)


def coerce_int(v: Any) -> Any:
    if is_int(v):
        return v
    if isinstance(v, float) and v.is_integer() and abs(v) < 1e15:
        return int(v)
    if isinstance(v, str) and v.strip() != "":
        try:
            f = float(v)
            if f.is_integer() and abs(f) < 1e15:
                return int(f)
        except ValueError:
            return v
    return v


def validate_plan(raw: Any) -> dict:
    if not isinstance(raw, dict):
        return {"ok": False, "error": "plan must be a JSON object"}
    qubits = coerce_int(raw.get("qubits"))
    if not is_int(qubits) or qubits < 1 or qubits > 4:
        return {"ok": False, "error": "qubits must be an integer 1–4"}
    gates = raw.get("gates")
    if not isinstance(gates, list):
        return {"ok": False, "error": "gates must be an array"}
    if len(gates) > MAX_GATES:
        return {"ok": False, "error": "at most 20 gates"}
    out_gates = []
    for i, g in enumerate(gates):
        if not isinstance(g, dict):
            return {"ok": False, "error": "gate %d is not an object" % i}
        op = as_string(g.get("op")).strip().upper()
        if op not in ALLOWED_OPS:
            shown = "(missing)" if g.get("op") is None else str(g.get("op"))
            return {"ok": False, "error": "unknown gate: %s" % shown}
        q = coerce_int(g.get("q"))
        if not is_int(q) or q < 0 or q >= qubits:
            return {
                "ok": False,
                "error": "gate %d (%s): q must be in 0..%d" % (i, op, qubits - 1),
            }
        if op in ONEQ:
            out_gates.append({"op": op, "q": q})
        elif op in TWOQ:
            t = coerce_int(g.get("t"))
            if not is_int(t) or t < 0 or t >= qubits:
                return {
                    "ok": False,
                    "error": "gate %d (%s): t must be in 0..%d" % (i, op, qubits - 1),
                }
            if q == t:
                return {
                    "ok": False,
                    "error": "gate %d (%s): q and t must be distinct" % (i, op),
                }
            out_gates.append({"op": op, "q": q, "t": t})
        elif op in ROT:
            theta = g.get("theta")
            if isinstance(theta, str) and theta.strip() != "":
                try:
                    theta = float(theta)
                except ValueError:
                    theta = None
            if isinstance(theta, bool) or not isinstance(theta, (int, float)):
                return {
                    "ok": False,
                    "error": "gate %d (%s): theta must be a finite number" % (i, op),
                }
            theta = float(theta)
            if theta != theta or theta in (float("inf"), float("-inf")):
                return {
                    "ok": False,
                    "error": "gate %d (%s): theta must be a finite number" % (i, op),
                }
            out_gates.append({"op": op, "q": q, "theta": theta})
    plan = {
        "title": as_string(raw.get("title")),
        "qubits": qubits,
        "gates": out_gates,
        "explain_th": as_string(raw.get("explain_th")),
        "explain_en": as_string(raw.get("explain_en")),
        "mapping": as_string(raw.get("mapping")),
        "is_toy": True,
    }
    return {"ok": True, "plan": plan}


def strip_fences(text: str) -> str:
    s = (text or "").strip()
    if not s.startswith("```"):
        return s
    lines = s.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def parse_plan_json(content: str) -> dict:
    s = strip_fences(content)
    if not s:
        return {"ok": False, "error": "empty assistant content"}
    try:
        obj = json.loads(s)
    except json.JSONDecodeError as e:
        start = s.find("{")
        end = s.rfind("}")
        if start >= 0 and end > start:
            try:
                obj = json.loads(s[start : end + 1])
            except json.JSONDecodeError:
                return {"ok": False, "error": "assistant content is not JSON: %s" % e}
        else:
            return {"ok": False, "error": "assistant content is not JSON: %s" % e}
    return validate_plan(obj)


def normalize_base(url: Any) -> str:
    if url is None or (isinstance(url, str) and not url.strip()):
        host = "api.moonshot.ai"
        return "https://%s/v1/chat/completions" % host
    if not isinstance(url, str):
        raise ValueError("base_url must be a string")
    u = url.strip()
    p = urlparse(u)
    if p.scheme != "https":
        raise ValueError("base_url must be https://api.moonshot.ai or https://api.moonshot.cn")
    host = (p.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise ValueError("base_url must be https://api.moonshot.ai or https://api.moonshot.cn")
    if p.username or p.password:
        raise ValueError("base_url must not include credentials")
    if p.query or p.fragment:
        raise ValueError("base_url must not include query or fragment")
    path = (p.path or "").rstrip("/") or ""
    if path in ("",):
        return "https://%s/v1/chat/completions" % host
    if path == "/v1":
        return "https://%s/v1/chat/completions" % host
    if path == "/v1/chat/completions":
        return "https://%s/v1/chat/completions" % host
    raise ValueError("base_url path not allowed")


def normalize_model(model: Any) -> str:
    if model is None or (isinstance(model, str) and not model.strip()):
        return DEFAULT_MODEL
    if not isinstance(model, str):
        raise ValueError("model must be a string")
    m = model.strip()
    if len(m) > 64:
        raise ValueError("model name too long")
    for ch in m:
        if not (ch.isalnum() or ch in "._-"):
            raise ValueError("model name has invalid characters")
    return m


def moonshot_chat(prompt: str, endpoint: str, model: str, key: str) -> dict:
    """Call Moonshot once. Returns {ok, content} or {ok: False, error, status}."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT + SCHEMA_HINT},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 800,
        "reasoning_effort": "low",
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + key,
    }

    def _do(body: bytes) -> dict:
        req = Request(endpoint, data=body, headers=headers, method="POST")
        try:
            with urlopen(req, timeout=90) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8", errors="replace")[:400]
            except Exception:
                err_body = ""
            return {
                "ok": False,
                "error": "Moonshot HTTP %s" % e.code,
                "status": e.code,
                "detail": err_body,
            }
        except URLError as e:
            return {"ok": False, "error": "Moonshot network error", "status": 502}
        except TimeoutError:
            return {"ok": False, "error": "Moonshot timed out", "status": 502}
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            return {"ok": False, "error": "Moonshot returned non-JSON", "status": 502}
        try:
            content = obj["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return {"ok": False, "error": "Moonshot response missing content", "status": 502}
        if content is None:
            content = ""
        if not isinstance(content, str):
            content = str(content)
        return {"ok": True, "content": content}

    result = _do(data)
    # If json_object is rejected, retry this attempt without it (still one logical try).
    if not result.get("ok") and result.get("status") in (400, 422):
        payload_plain = dict(payload)
        payload_plain.pop("response_format", None)
        result = _do(json.dumps(payload_plain).encode("utf-8"))
    return result


def plan_from_kimi(prompt: str, endpoint: str, model: str, key: str) -> dict:
    """One user request: call Kimi, parse JSON. Retry at most once on network/parse fail."""
    last_err = "Kimi request failed"
    for attempt in range(2):
        result = moonshot_chat(prompt, endpoint, model, key)
        if not result.get("ok"):
            last_err = result.get("error") or last_err
            # Retry network-ish failures only.
            if result.get("status") in (400, 401, 403, 404, 422):
                return {"ok": False, "error": last_err, "http": 502}
            continue
        parsed = parse_plan_json(result["content"])
        if parsed.get("ok"):
            return {"ok": True, "plan": parsed["plan"]}
        last_err = parsed.get("error") or "invalid JSON from Kimi"
        # Parse fail: retry once. Validation reject: do not retry.
        if last_err.startswith("unknown gate") or last_err.startswith("qubits") or last_err.startswith("gate "):
            return {"ok": False, "error": last_err, "http": 422}
        if last_err.startswith("at most") or last_err.startswith("gates must"):
            return {"ok": False, "error": last_err, "http": 422}
        if last_err.startswith("plan must"):
            return {"ok": False, "error": last_err, "http": 422}
        # parse / empty: retry
    # After retry, classify
    if last_err.startswith("unknown gate") or last_err.startswith("qubits") or last_err.startswith("gate "):
        return {"ok": False, "error": last_err, "http": 422}
    if last_err.startswith("at most") or last_err.startswith("gates must") or last_err.startswith("plan must"):
        return {"ok": False, "error": last_err, "http": 422}
    if "not JSON" in last_err or "empty assistant" in last_err:
        return {"ok": False, "error": last_err, "http": 502}
    return {"ok": False, "error": last_err, "http": 502}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt: str, *args: Any) -> None:
        # Path + status only. Never log bodies, headers, or env.
        sys.stderr.write("%s %s\n" % (self.command, getattr(self, "path", "")))

    def _send_json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> Any:
        n = int(self.headers.get("Content-Length") or "0")
        if n < 0 or n > 200_000:
            raise ValueError("request body too large")
        raw = self.rfile.read(n) if n else b""
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            self._send_json(
                200,
                {
                    "ok": True,
                    "proxy": True,
                    "qpanda_present": qpanda_present(),
                },
            )
            return
        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/origin/test":
            self._origin_test()
            return
        if path == "/origin/sample":
            self._origin_sample()
            return
        if path == "/origin/job":
            self._origin_job()
            return
        if path != "/plan":
            self._send_json(404, {"error": "not found"})
            return
        try:
            body = self._read_json_body()
        except Exception:
            self._send_json(400, {"error": "request body must be JSON"})
            return
        if not isinstance(body, dict):
            self._send_json(400, {"error": "request body must be a JSON object"})
            return
        moonshot_key = body.get("moonshot_key")
        if not isinstance(moonshot_key, str):
            moonshot_key = ""
        moonshot_key = moonshot_key.strip()
        if not moonshot_key:
            self._send_json(400, {"error": "moonshot_key is required. Paste your Moonshot API key in Settings."})
            return
        prompt = body.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            self._send_json(400, {"error": "prompt must be a non-empty string"})
            return
        prompt = prompt.strip()
        if len(prompt) > MAX_PROMPT:
            self._send_json(400, {"error": "prompt too long"})
            return
        try:
            endpoint = normalize_base(body.get("base_url"))
            model = normalize_model(body.get("model"))
        except ValueError as e:
            self._send_json(400, {"error": str(e)})
            return
        try:
            result = plan_from_kimi(prompt, endpoint, model, moonshot_key)
        except Exception:
            self._send_json(502, {"error": "proxy failed calling Kimi"})
            return
        if not result.get("ok"):
            code = int(result.get("http") or 502)
            self._send_json(code, {"error": result.get("error") or "plan failed"})
            return
        self._send_json(200, result["plan"])



    def _origin_body(self) -> dict | None:
        try:
            body = self._read_json_body()
        except Exception:
            self._send_json(400, {"error": "request body must be JSON"})
            return None
        if not isinstance(body, dict):
            self._send_json(400, {"error": "request body must be a JSON object"})
            return None
        return body

    def _origin_test(self) -> None:
        body = self._origin_body()
        if body is None:
            return
        key = body.get("key")
        if key is None:
            key = ""
        if not isinstance(key, str):
            self._send_json(400, {"error": "key must be a string"})
            return
        try:
            result = origin_test(key)
        except Exception as e:
            self._send_json(502, {"ok": False, "error": sanitize_error(e, key)})
            return
        code = 200 if result.get("ok") else 400
        self._send_json(code, result)

    def _origin_sample(self) -> None:
        body = self._origin_body()
        if body is None:
            return
        key = body.get("key")
        if key is None:
            key = ""
        if not isinstance(key, str):
            self._send_json(400, {"error": "key must be a string"})
            return
        qasm = body.get("qasm")
        device = body.get("device") or DEFAULT_DEVICE_ORIGIN
        shots = body.get("shots")
        n = body.get("qubits")
        if n is None:
            n = body.get("n")
        if not isinstance(qasm, str):
            self._send_json(400, {"error": "qasm must be a string"})
            return
        if not isinstance(device, str):
            self._send_json(400, {"error": "device must be a string"})
            return
        try:
            result = origin_sample(key, qasm, device, shots or DEFAULT_SHOTS_ORIGIN, n)
        except Exception as e:
            self._send_json(502, {"ok": False, "error": sanitize_error(e, key)})
            return
        code = 200 if result.get("ok") else 400
        self._send_json(code, result)

    def _origin_job(self) -> None:
        body = self._origin_body()
        if body is None:
            return
        key = body.get("key")
        if key is None:
            key = ""
        if not isinstance(key, str):
            self._send_json(400, {"error": "key must be a string"})
            return
        try:
            result = origin_job(key, body.get("job_id"), body.get("qubits") if body.get("qubits") is not None else body.get("n"))
        except Exception as e:
            self._send_json(502, {"ok": False, "error": sanitize_error(e, key)})
            return
        code = 200 if result.get("ok") else 400
        self._send_json(code, result)


def main() -> None:
    os.chdir(ROOT)
    # ThreadingHTTPServer = socketserver.ThreadingMixIn + HTTPServer (stdlib).
    # Origin poll must not freeze static files or /plan (Kimi).
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print("ทดลองควอนตัม.com proxy on http://%s:%d" % (HOST, PORT), flush=True)
    print("qpanda_present=%s" % ("true" if qpanda_present() else "false"), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye", flush=True)


if __name__ == "__main__":
    main()
