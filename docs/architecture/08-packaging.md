# Entropy Architecture Handbook

# Stage 8 — Packaging, Installation and Upgrades

Version: 1.0

Status: Implemented (Linux x86_64 verified; other platforms built, untested)

---

# Purpose

Entropy ships as **one file per platform**: a `tar.gz` that carries a
Python runtime, the application, the built web UI and every Python
package. Installing needs no Python, pip, virtual environment or npm on
the server; upgrading is one command or one upload in the UI.

---

# Release package

```
entropy-<version>-<platform>.tar.gz
└── entropy-<version>/
    ├── install.sh | install.cmd     installer entry point (per OS)
    ├── manifest.json                format 2, name, version, platform, python, built_at
    ├── README.txt
    ├── python/                      CPython 3.9 (python-build-standalone, install_only)
    └── application/
        ├── core/ lib/ entropy.py …
        ├── frontend/dist/           built web UI, served by the web server
        └── resources/wheels/
            ├── requirements.txt
            └── <linux|mac|windows>/ wheels for this platform only
```

Platforms: `linux-x86_64`, `linux-aarch64`, `macos-arm64`,
`macos-x86_64`, `windows-x86_64`. A `.sha256` file is written next to
each archive.

## Building

```
python3 scripts/release.py --platform linux-x86_64          # one platform
python3 scripts/release.py --all --version 1.3.0            # every platform
```

| Option | Notes |
|---|---|
| `--platform` (repeatable), `--all` | Target platforms. |
| `--version` | Overrides `core/version.py` inside the package. |
| `--skip-frontend` | Reuse `frontend/dist` instead of `npm ci && npm run build`. |
| `--wheels DIR`, `--python-archive FILE` | Offline builds from pre-downloaded inputs. |
| `--output DIR` | Default `build/dist/`. |

Wheels are resolved with `pip download --only-binary=:all:` for CPython
3.9 and the target platform tags. The resolver itself runs on a host
CPython 3.9 (downloaded into `build/cache/host-python`) so that markers
such as `python_version < "3.10"` resolve as they will at run time.
Downloads are cached under `build/cache/`.

Any host can build any platform's package. The bundled Python is copied
member by member from its CPython archive into the package, never
extracted on the build host, so the host's file system cannot alter it
(macOS is case-insensitive and the Linux runtime's terminfo has names
differing only in case; Windows drops symlinks and permission bits).
Application files get fixed permissions: directories 755, files 644,
`install.sh` 755.

---

# Installation

```
tar xzf entropy-1.3.0-linux-x86_64.tar.gz
./entropy-1.3.0/install.sh            # Windows: install.cmd
```

The installer asks for:

1. **Python packages** — bundled wheels (offline, default), a package
   index, or packages installed manually into the chosen Python.
2. **Workspace** — the workflow workspace directory.
3. **Bootstrap administrator** — username (default `admin`) and
   password.

It then installs for the current user and starts the web server, as a
systemd user service (`entropy-web`, with lingering enabled) when
systemd is available, otherwise as a background process.

Unattended:

```
ENTROPY_ADMIN_PASSWORD='…' ./install.sh --yes --workspace /srv/entropy --port 8000
./install.sh --yes --workspace ~/ws --admin-password-file pw.txt --deps index \
    --index-url https://pypi.example.com/simple
./install.sh --python=/opt/py39/bin/python --deps manual --yes …
./install.sh --print-requirements     # what --deps manual expects
./install.sh uninstall
```

| Option | Notes |
|---|---|
| `--workspace`, `--admin-user`, `--admin-name`, `--admin-password-file` | Skip the prompts. The password can also come from `ENTROPY_ADMIN_PASSWORD` (removed from the environment once read). |
| `--deps bundled\|index\|manual`, `--index-url` | Python package source. |
| `--python=PATH` / `ENTROPY_PYTHON` | Run on another Python 3.9+ instead of the bundled one (typical with `--deps manual`). |
| `--host`, `--port` | Web server address (default `127.0.0.1:8000`). |
| `--service auto\|systemd\|none`, `--no-start` | How and whether to start the web server. |
| `-y`, `--yes` | Never prompt. |

## Layout after installation

| Path | Contents |
|---|---|
| `~/.local/share/entropy/application` | The application (replaced by upgrades). |
| `~/.local/share/entropy/python` | The bundled Python, when used. |
| `~/.local/bin/ent` | Launcher. |
| `~/.entropy/` (`ENTROPY_HOME`) | Data: database, configuration, plugins, logs, sessions. |
| `~/.entropy/site-packages` | Python packages (bundled and index modes). |
| `~/.entropy/config/install.json` | The installation record (below). |

`install.json` records the version, the Python, the package mode and
index URL, the platform, the web server address and supervisor, and the
upgrade history, so upgrades repeat the choices made at install time.

## Web server

`python -m core.web` serves the API and the built UI from
`frontend/dist` (`ENTROPY_WEB_DIST` overrides it). Unknown paths fall
back to `index.html`; hashed files under `/assets` are cached as
immutable. `ent web start|stop|restart|status` manages it through
systemd or a pid file (`~/.entropy/run/web.pid`, log
`~/.entropy/logs/web.log`).

---

# Upgrades

From a terminal (requires `upgrade.entropy`):

```
ent upgrade --source entropy-1.4.0-linux-x86_64.tar.gz --check   # inspect only
ent upgrade --source entropy-1.4.0-linux-x86_64.tar.gz           # apply
ent upgrade --rollback                                           # undo the last upgrade
```

From the UI: **Administration → System** — upload the package, review
it, apply it and follow the log. The page reloads itself on the new
version once the server is back. The same page shows the installation
details and history and offers **Roll back**.

## Steps

1. **Inspect** — `manifest.json` must be format 2 for this installation's
   platform, and the version newer (or `--allow-downgrade`). Source
   checkouts (no `install.json`) are refused.
2. **Extract** into `<install root>/upgrade-staging`, refusing absolute
   paths, `..`, device files and links that point outside the package.
3. **Install Python packages** into `~/.entropy/site-packages.new`
   using the recorded mode (manual mode only verifies them).
4. **Swap** application, site-packages and — when the package brings a
   different Python version — the bundled Python. The replaced copies
   are kept as `*.previous`.
5. **Finalize** with the *new* code (`python -m lib.system.finalize`):
   back up the database (`entropy.before-<version>.db`, SQLite online
   backup), migrate, reconcile built-in permissions. A migration that
   fails restores the backup itself.
6. **Restart** the web server (`ent upgrade` restarts a running server;
   the UI re-executes its own process in place, keeping the pid).

If any step fails, every swap is undone and the database restored, so the
installation stays on the previous version. An upgrade lock
(`~/.entropy/run/upgrade.lock`) prevents concurrent upgrades.

## Rollback

Rollback returns the `*.previous` application, packages and Python and
restores the database backup taken before the last upgrade. **Changes
made since that upgrade are lost**; the CLI and UI both say so before
proceeding. Only the last upgrade can be rolled back.

## Upgrade API

| Method | Path | Notes |
|---|---|---|
| GET | `/api/system` | Installation, web server, history, `can_rollback`, current job. |
| POST | `/api/system/upgrade/package` | Upload (multipart `file`); returns the inspection. Only the latest upload is kept. |
| DELETE | `/api/system/upgrade/package/{id}` | Discard an upload. |
| POST | `/api/system/upgrade` | `{id, allow_downgrade}`; starts the upgrade (202). |
| POST | `/api/system/rollback` | Starts a rollback (202). |
| GET | `/api/system/upgrade` | Job state (`running`, `restarting`, `succeeded`, `failed`) and log. |

Job state lives in `~/.entropy/run/upgrade-status.json` because the
server restarts during an upgrade.
