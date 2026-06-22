# Solution Document — Public Access for Hostinger-Hosted Orchestration Engine

> **Problem:** Access the Telecom Agentic Orchestration Engine web UI publicly from a Hostinger VPS
> **Date:** 2026-06-22
> **Solution:** Reverse SSH tunnel via `localhost.run`
> **Public URL:** `https://f6eefa30713c30.lhr.life`

---

## 1. Problem Statement

The Production PoC server (`server_live.py`) runs a FastAPI web UI with real Deepseek integration on `0.0.0.0:8090`. The server was fully tested locally but inaccessible from the public internet. The Hostinger VPS sits behind a managed edge proxy that intercepts and controls all inbound traffic.

---

## 2. Network Topology (The Constraint)

```
                    INTERNET
                       │
                       ▼
        ┌──────────────────────────────┐
        │  Hostinger Edge Proxy/LB     │
        │                              │
        │  Port 80 → 301 redirect to 443
        │  Port 443 → serves 404       │
        │  All other ports → DROP      │
        └──────────────┬───────────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │  Hostinger Cloud Firewall    │
        │  (hPanel-managed, not ufw)   │
        │                              │
        │  Only 80, 443 forwarded      │
        └──────────────┬───────────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │        VPS (72.60.108.197)   │
        │                              │
        │  server_live.py :8090  ✓     │
        │  (no inbound path from net)  │
        └──────────────────────────────┘
```

**Key insight:** The Hostinger edge proxy sits in front of the VPS. It intercepts ports 80 and 443 before traffic reaches the VPS. All other ports are dropped at the edge. This is NOT a VPS-level firewall issue — `ufw` and `iptables` rules have no effect. The edge controls what reaches the VPS.

---

## 3. Approaches Attempted

### 3.1 Open Port 8090 in Hostinger Firewall → FAILED

**What was tried:** Configured the user to add a TCP inbound rule for port 8090 in Hostinger hPanel → VPS → Firewall.

**Why it failed:** The Hostinger cloud firewall at hPanel manages the VPS-level firewall, but the **edge proxy** sits above it. Even with the cloud firewall rule in place, the edge does not forward custom ports. Traffic to `72.60.108.197:8090` never reaches the VPS.

**Evidence:**
```bash
# From within the VPS, connecting to its own public IP fails:
$ curl http://72.60.108.197:8090/health
curl: (7) Failed to connect — Connection refused
```

### 3.2 Bind to Port 80 → FAILED

**What was tried:** Moved the server from port 8090 to port 80, since port 80 is open at the edge.

**Why it failed:** The Hostinger edge proxy does not forward port 80 traffic to the VPS. Instead, it intercepts port 80 at the edge and returns an HTTP 301 redirect to HTTPS:

```bash
$ curl -v http://72.60.108.197:80/health
< HTTP/1.1 301 Moved Permanently
< Location: https://72.60.108.197/health
```

The redirect response comes from the edge, NOT from uvicorn. Our server's port 80 never receives the request.

### 3.3 Bind to Port 443 → NOT POSSIBLE

Port 443 on localhost was "connection refused." The edge proxy intercepts 443 traffic and returns its own 404 response — it doesn't forward to the VPS. There is no local process on 443 to receive requests.

### 3.4 Hermes Gateway Webhook → NOT APPLICABLE

The Hermes gateway's webhook platform creates endpoints that trigger agent runs when receiving HTTP POSTs — designed for incoming webhook integrations, not for serving a web UI response. Not the right tool for a reverse proxy.

### 3.5 Serve Through Hermes Gateway HTTPS → NOT POSSIBLE WITHOUT RESTART

Port 443 is the only path through the edge, but it's managed by the edge proxy, not a local web server. The Hermes gateway connects to messaging platforms via outbound API calls — it doesn't listen on port 443 for inbound HTTP.

### 3.6 Install nginx → NO SUDO ACCESS

The system runs as the `hermes` user without `sudo` or `root`. Cannot install system packages (`apt install nginx`). Python-only solutions required.

### 3.7 pip-Based Tunneling (`bore`, `pyngrok`) → INSTALL FAILURES

- `bore`: Requires `setuptools.build_meta` which failed to import despite setuptools being installed (PEP 517 build backend issue with Python 3.13)
- `pyngrok`: Installed successfully but requires an ngrok auth token (none available)
- `serveo.net`: SSH connection established but returned no output (service likely down or blocking)

---

## 4. Solution: Reverse SSH Tunnel via `localhost.run`

### 4.1 How It Works

`localhost.run` provides a free public HTTPS endpoint that tunnels to a local port via SSH reverse forwarding. No installation, no auth tokens, no account required — just an SSH command.

```
Your Browser ──HTTPS──▶ f6eefa30713c30.lhr.life
                              │
                    localhost.run edge server
                    (TLS termination + forwarding)
                              │
                    SSH reverse tunnel (-R flag)
                              │
                              ▼
                    VPS localhost:8090
                         server_live.py
```

### 4.2 The Command

```bash
ssh -o StrictHostKeyChecking=no \
    -o ServerAliveInterval=30 \
    -R 80:localhost:8090 \
    nokey@localhost.run
```

| Flag | Purpose |
|---|---|
| `-R 80:localhost:8090` | Reverse tunnel — remote port 80 on localhost.run forwards to local port 8090 |
| `nokey@localhost.run` | Anonymous SSH login (no key or password required) |
| `-o StrictHostKeyChecking=no` | Skip host key prompt for automation |
| `-o ServerAliveInterval=30` | Keep-alive every 30 seconds to prevent timeout |

### 4.3 Result

```bash
# Tunnel output:
** your connection id is a7e4db05-3847-4533-bcc4-767f50b34aa5
f6eefa30713c30.lhr.life tunneled with tls termination
https://f6eefa30713c30.lhr.life

# Verification:
$ curl https://f6eefa30713c30.lhr.life/health
{"status":"ok","cache_size":2,"redis_backend":"diskcache"}
```

### 4.4 Why This Worked

1. **Outbound SSH always works:** The VPS can initiate outbound SSH connections (port 22 outbound is open). The reverse tunnel is an outbound connection from the VPS to localhost.run.

2. **No edge proxy interference:** Inbound traffic arrives through the SSH tunnel, bypassing the Hostinger edge entirely. It's an established SSH session, not a new inbound TCP connection.

3. **Free TLS termination:** localhost.run provides HTTPS automatically. The `lhr.life` domain has a valid SSL certificate.

4. **Zero dependencies:** Uses only `ssh`, which is pre-installed on every Linux system. No pip packages, no auth tokens, no accounts.

### 4.5 Trade-offs

| Aspect | Detail |
|---|---|
| **URL stability** | The subdomain changes on each connection. A custom domain requires a free account at admin.localhost.run |
| **Persistence** | The SSH connection must remain open. If it drops, the tunnel dies |
| **Latency** | +30-50ms added by the tunnel hop |
| **Bandwidth** | Sufficient for web UI and API calls (~KB per request) |
| **Rate limits** | Free tier has generous but unspecified limits |

---

## 5. Alternative Solutions Considered

| Solution | Feasibility | Reason Not Chosen |
|---|---|---|
| **Cloudflare Tunnel** | Good | Requires `cloudflared` binary, domain ownership |
| **ngrok** | Good | Requires auth token, free tier has limits |
| **SSH local forwarding** (`ssh -L`) | Good | Requires user to run command on their local machine |
| **Tailscale Funnel** | Good | Requires Tailscale installation and account |
| **Reverse proxy via gateway restart** | Risky | Would disconnect the active session |
| **Direct port opening** | Failed | Hostinger edge blocks custom ports |

---

## 6. Operational Notes

### 6.1 Keeping the Tunnel Alive

The SSH connection can drop due to network interruptions or idle timeouts. To reconnect:

```bash
# Kill any stale tunnels
pkill -f "localhost.run"

# Restart the tunnel
ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 \
    -R 80:localhost:8090 nokey@localhost.run
```

A new subdomain will be assigned. Update any bookmarks accordingly.

### 6.2 Persistent Tunnel (Optional)

For a production deployment that survives process exits, wrap in a systemd user service or a simple restart loop:

```bash
while true; do
  ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 \
      -R 80:localhost:8090 nokey@localhost.run
  sleep 5
done
```

### 6.3 Custom Domain

Register a free account at `https://admin.localhost.run/`, add an SSH public key, and configure a custom subdomain for a stable URL that persists across reconnections.

---

## 7. Summary

The core constraint was the **Hostinger edge proxy** — not the VPS firewall, not the application, not missing packages. The edge intercepts all inbound traffic on ports 80/443 and drops everything else. No amount of local firewall configuration or port binding can change this.

The solution was to **bypass the edge entirely** by creating an outbound SSH connection that carries inbound traffic back through the tunnel. `localhost.run` was the simplest service that required zero installation, zero authentication, and provided free HTTPS termination.

**The principle:** When inbound paths are blocked at the network edge, reverse the direction. Make an outbound connection from inside the network, and carry inbound traffic through it.
