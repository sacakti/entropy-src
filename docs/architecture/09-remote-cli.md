# Entropy Architecture Handbook

# Stage 9 — Remote Command Line (`ent` against a server URL)

Version: 1.0

Status: Implemented

---

# Purpose

Run `ent` commands — `ent login`, `ent workflow run`, `ent job logs` … —
from any machine, including execution nodes, against an Entropy server
URL, the way `oc login https://cluster` works for OpenShift. The client
talks to the web API; it needs no database, workspace or Entropy install.

There are two ways to get it:

1. **While registering a node.** *Add node → Advanced → Install the ent
   command line* (on by default). Setup installs `~/.local/bin/ent` for the
   SSH user, pointed at the main node URL. On the node: `ent login`.
2. **The installer, from the server itself** (any Linux, macOS or Windows
   machine with Python 3.9+):

   ```sh
   curl -fsSL https://entropy.example.com/api/cli/install.sh | sh
   ent login https://entropy.example.com
   ```

   ```powershell
   irm https://entropy.example.com/api/cli/install.ps1 | iex
   ```

   **Help → Remote command line** in the web UI shows these commands for
   the server you are on, and **Copy login command with a token** gives an
   `ent login <url> --token …` that needs no password (handy for scripts).

---

# The client

`lib/remote_cli` — standard library only, Python 3.9+.

| Module | Role |
|---|---|
| `config.py` | Contexts in `~/.entropy-cli/config.json` (mode 0600; `ENT_CONFIG` to move it). |
| `api.py` | HTTP client: bearer token, TLS options, readable errors. |
| `commands.py` | The command tree. |
| `build.py` | Packs the client as one zipapp, `ent.pyz`. |

The server builds `ent.pyz` from these sources on first request (cached
until they change), so the client always matches the server's version.

## Contexts

Each server you log in to is a *context* named after its host and port.

```sh
ent login https://prod.example.com          # prompts; becomes current
ent login https://staging.example.com -u ci --password-stdin < pw.txt
ent context list
ent context use prod.example.com
ENT_CONTEXT=staging.example.com ent job list   # one command elsewhere
ent --context staging.example.com job list
```

TLS: `--certificate-authority FILE` for a private CA,
`--insecure-skip-tls-verify` for a self-signed certificate (both are saved
in the context). Non-interactive login: `--password-stdin`, `ENT_PASSWORD`,
or `--token`.

## Commands

| Command | Does |
|---|---|
| `ent login [URL]`, `ent logout`, `ent whoami`, `ent status`, `ent version` | Session (also `ent auth login/logout/whoami/status`). |
| `ent context list/use/delete` | Contexts (`ctx`). |
| `ent workflow list/get/validate/apply/delete/run/history/restore` | Workflows (`wf`). `apply -f FILE` creates or updates. `run --var K=V --tag T --step S --node N --step-node S=N --follow`. |
| `ent job list/get/logs/stop/wait` | Runs (`jobs`, `run`, `runs`). `logs -f` follows; `wait` exits 0 completed, 1 failed, 130 cancelled. |
| `ent plugin list/run`, `ent node list`, `ent schedule list` | |

Most list and get commands take `-o json` for scripts. Every command uses
the permissions of the logged-in user, exactly as the web UI does.

---

# Server side

| Method | Path | |
|---|---|---|
| POST | `/api/auth/token` | `{username, password}` → `{token, expires_at, user}`. |
| POST | `/api/auth/cli-token` | Token for the signed-in browser user (CSRF-protected). |
| DELETE | `/api/auth/token` | Revokes the bearer token of the request. |
| GET | `/api/cli` | Install and login commands for this server. |
| GET | `/api/cli/ent.pyz`, `/api/cli/install.sh`, `/api/cli/install.ps1` | Downloads (public: they hold no secrets). |

- Every API route accepts `Authorization: Bearer <token>` as well as the
  browser cookie. A token is an ordinary web session with a longer life:
  `auth.cli.timeout` hours (default 168, one week).
- Bearer requests skip the CSRF check: a browser never attaches an
  `Authorization` header to a cross-site request on its own.
- The server URL in the installers comes from the request (or
  `X-Forwarded-Proto`/`X-Forwarded-Host` behind a proxy) and must look
  like a plain `http(s)://host[:port]`, so nothing else reaches the
  generated scripts.

# Security notes

- The token file is private to the user (0600, directory 0700).
- `ent logout` revokes the token on the server, not only locally.
- On an Entropy server the local `ent` (with database access) is already
  installed; the installer refuses to overwrite an `ent` it did not write.
  Use `ENT_NAME=entr` to install the remote client under another name.
- On nodes the wrapper uses the agent's Python runtime and the client
  code it already has; removing the node removes the wrapper.
