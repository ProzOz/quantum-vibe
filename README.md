# ทดลองควอนตัม.com · Try Quantum

Teaching prototype running on Python proxy. Visitors paste **their own** Moonshot and Origin API keys in Settings. Circuits are simulated in the browser (1–4 qubits, statevector + shots). This does **not** claim quantum advantage.

The GitHub repo folder stays `quantum-vibe` (not renamed).

## For visitors (public Coolify deploy)

1. Open **ทดลองควอนตัม.com** (owner will bind this domain on Coolify after merge)
2. Open **Settings**
3. Paste **your Moonshot API key** (for Kimi K3 circuit generation)
4. Paste **your Origin API key** (optional, for Wukong 180 real QPU)
5. Keys stay in your browser only (`localStorage`). Never logged. Not stored on the server.
6. Preset chips + in-browser sim work with **no keys**.

## Local development

```bash
cd /path/to/quantum-vibe
HOST=127.0.0.1 PORT=8787 python proxy.py
```

Open [http://127.0.0.1:8787](http://127.0.0.1:8787)

- Visitors paste keys in Settings (localStorage on their browser)
- `GET /health` reports `{ok, proxy, qpanda_present}` — never reports keys
- `POST /plan` requires `moonshot_key` in JSON body (client-provided, returns 400 if missing)
- Origin routes (`/origin/test`, `/origin/sample`, `/origin/job`) take `key` from JSON body

Python 3 stdlib only (`http.server` + `urllib`). HOST default `0.0.0.0`, PORT default `3000` (Coolify). Local can override with env.

## Origin Wukong 180 (optional)

Local sim is the default. After a circuit exists, **ยิงเข้า Wukong 180 จริง** can submit OpenQASM to `WK_C180` at 256 shots. Confirm first. No auto-send.

- Settings: Origin API key (password, `localStorage` on visitor's browser only) and device id (default `WK_C180`)
- **Test key** calls `POST /origin/test` (login + list devices). No submit.
- Submit is `POST /origin/sample` (async: returns `job_id` immediately, never waits on the chip). Browser polls `POST /origin/job` every 10s for up to 20 minutes. 256 shots. Proxy never logs the key.
- A real chip queue can take many minutes. Local bars stay. Results are never faked.
- Needs `qpanda3-runtime` and `pyqpanda3` at runtime (Dockerfile tries to install; local devs `pip install` manually).

## Coolify deploy (public, on ทดลองควอนตัม.com)

`Dockerfile` runs Python proxy on port **3000**. Coolify binds **ทดลองควอนตัม.com** to this app (separate from เรียนควอนตัม.com, which is `ProzOz/quantum-experience`).

**Owner must NOT set `MOONSHOT_API_KEY` or Origin keys as Coolify env.** Visitors paste keys in Settings.

In-browser sim and preset chips work with no keys. Kimi needs a Moonshot key; Wukong needs an Origin key (both visitor-provided).

After merge, owner **Redeploys** Coolify with the new app pointing at this repo.

This does not claim quantum advantage, real users, or KMITL admission.
