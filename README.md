# ทดลองควอนตัม.com · Try Quantum

Teaching prototype running on a Python proxy. Circuits are simulated in the browser (1–4 qubits, statevector + shots). This does **not** claim quantum advantage.

The GitHub repo folder stays `quantum-vibe` (not renamed).

## For visitors (public Coolify deploy)

1. Open **ทดลองควอนตัม.com**
2. Type a prompt and **Run** — Kimi K3 works **without** pasting a Moonshot key when the owner has set the server env var
3. Optional: open **Settings** and paste **your own** Moonshot key if you want to use yours instead of the shared one
4. Optional: paste a **free Origin API key** (for Wukong 180 real QPU). Origin is never a shared server default — you get your own free-tier key
5. Visitor-pasted keys stay in the browser only (`localStorage`). Never logged. Not stored on the server
6. Preset chips + in-browser sim work with **no keys**

The yellow honesty banner stays: this is a teaching toy. Real chips are slow, expensive, and noisy.

## Local development

```bash
cd /path/to/quantum-vibe
HOST=127.0.0.1 PORT=8787 python proxy.py
```

Open [http://127.0.0.1:8787](http://127.0.0.1:8787)

- `GET /health` reports `{ok, proxy, qpanda_present, kimi_shared}` — `kimi_shared` is a boolean only. **Never** reports the secret
- `POST /plan` uses `moonshot_key` from the JSON body if the visitor pasted one; otherwise the server env key
- Origin routes (`/origin/test`, `/origin/sample`, `/origin/job`) still take `key` from the JSON body (visitor-pasted)

Python 3 stdlib only (`http.server` + `urllib`). HOST default `0.0.0.0`, PORT default `3000` (Coolify). Local can override with env.

```bash
python test-proxy.py
node test-bind.js
```

## Shared Kimi (Coolify env)

Set **one** secret on the Coolify app. Do **not** put the value in git, README, frontend JS, or Settings defaults.

| Env var | Role |
| --- | --- |
| `MOONSHOT_API_KEY` | Preferred. Owner Moonshot / Kimi key used when Settings is blank |
| `KIMI_API_KEY` | Alias if `MOONSHOT_API_KEY` is unset |

Visitor key in Settings **wins** when present. Empty Settings → proxy uses the env key.

Light abuse protection on `POST /plan`: 8 requests / IP / 60s, 800 max tokens, 25s timeout. Shared-key requests are locked to model `kimi-k3`.

## Origin Wukong 180 (optional, visitor key)

Local sim is the default. After a circuit exists, **ยิงเข้า Wukong 180 จริง** can submit OpenQASM to `WK_C180` at 256 shots. Confirm first. No auto-send.

- Settings: Origin installer is a free / free-tier how-to. Paste your own key (`localStorage` on the visitor's browser only). Device id default `WK_C180`
- **Do not** set Origin keys as a Coolify shared default
- **Test key** calls `POST /origin/test` (login + list devices). No submit
- Submit is `POST /origin/sample` (async: returns `job_id` immediately). Browser polls `POST /origin/job` every 10s for up to 20 minutes. 256 shots. Proxy never logs the key
- A real chip queue can take many minutes. Local bars stay. Results are never faked
- Needs `qpanda3-runtime` and `pyqpanda3` at runtime (Dockerfile tries to install; local devs `pip install` manually)

## Coolify deploy (public, on ทดลองควอนตัม.com)

`Dockerfile` runs Python proxy on port **3000**. Coolify binds **ทดลองควอนตัม.com** to this app (separate from เรียนควอนตัม.com, which is `ProzOz/quantum-experience`).

**Owner: set `MOONSHOT_API_KEY` (or `KIMI_API_KEY`) as a Coolify secret, then Redeploy.** Do not commit the value. Do not set Origin keys as shared env.

After merge, owner **Redeploys** Coolify with the new app pointing at this repo.

This does not claim quantum advantage, real users, or KMITL admission.
