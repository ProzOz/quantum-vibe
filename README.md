# Quantum Vibe / ควอนตัมไวบ์

Local teaching prototype. The browser talks **only** to a proxy on `127.0.0.1`. Circuits are simulated in the browser (1–4 qubits, statevector + shots). This does **not** claim quantum advantage. City-scale traffic and real drug screening are mapped to tiny teaching circuits.

You do **not** need `file://`. Open the app through the proxy.

## API key (placeholder only — never commit a real key)

The proxy reads `MOONSHOT_API_KEY` from the process environment. The key is never stored in HTML, JS, CSS, or this README.

Windows PowerShell:

```powershell
$env:MOONSHOT_API_KEY = "YOUR_MOONSHOT_KEY"
```

Windows Command Prompt (cmd):

```cmd
set MOONSHOT_API_KEY=YOUR_MOONSHOT_KEY
```

Then, in the same window:

## Start the proxy

```cmd
cd C:\Users\Admin\quantum-vibe
python proxy.py
```

Open [http://127.0.0.1:8787](http://127.0.0.1:8787)

- Default API base: `https://api.moonshot.ai` (Settings can switch to `https://api.moonshot.cn`)
- Default model: `kimi-k3`
- `GET /health` reports `{ok, proxy, key_present}` — boolean only, never the key
- Free-text **Run** posts to `/plan` (one request; retry at most once on network/parse failure)
- Preset chips run canned demos locally and do **not** call Kimi
- If the key is missing, Kimi is down, or JSON is invalid: the app shows the error and offers presets as an explicit fallback. It never silently swaps in a canned demo.

Python 3 stdlib only (`http.server` + `urllib`). Bind is `127.0.0.1:8787`.

## Origin Wukong 180 (optional)

Local sim is the default. After a circuit exists, **ยิงเข้า Wukong 180 จริง** can submit OpenQASM to `WK_C180` at 256 shots. Confirm first. No auto-send.

- Settings: Origin API key (password, `localStorage origin_key` on this machine only) and device id (default `WK_C180`)
- **Test key** calls `POST /origin/test` (login + list devices). No submit.
- Submit is `POST /origin/sample` (async: returns `job_id` immediately, never waits on the chip). Browser polls `POST /origin/job` every 10s for up to 20 minutes. 256 shots. Proxy never logs the key.
- A real chip queue can take many minutes. Local bars stay. Results are never faked.

Restart `python proxy.py` in the same window that already has `MOONSHOT_API_KEY` so the new routes load.

## Coolify (static demo)

Same pattern as the other site: `Dockerfile` + `nginx` on port **3000**. In-browser 1–4 qubit sim and preset chips work with no API keys.

Kimi (`/plan`) and Origin Wukong stay on your machine via `python proxy.py` at `http://127.0.0.1:8787`. Do **not** put `MOONSHOT_API_KEY` or an Origin key on Coolify. Do **not** reuse เรียนควอนตัม.com.

After GitHub has `main`, add a Coolify app on this repo and **Redeploy** yourself.

This does not claim quantum advantage, real-QPU access from the public URL, users, or KMITL admission.
