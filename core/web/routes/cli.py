"""
Download the `ent` command line for remote servers (like `oc`):

    curl -fsSL https://entropy.example.com/api/cli/install.sh | sh
    ent login https://entropy.example.com

These endpoints are public: the client holds no secrets.
"""

# ruff: noqa: E501 - the installer scripts below keep their natural lines.

from __future__ import annotations

import re
from typing import Any, Dict, Tuple

from fastapi import APIRouter, Request, Response
from fastapi.responses import PlainTextResponse

from core.version import VERSION
from lib.remote_cli.build import build_pyz, fingerprint

router = APIRouter(prefix="/api/cli", tags=["command line"])

_CACHE: Dict[str, Tuple[str, bytes]] = {}


def _pyz() -> bytes:
    key = f"{VERSION}:{fingerprint()}"
    cached = _CACHE.get("pyz")
    if cached is None or cached[0] != key:
        _CACHE["pyz"] = (key, build_pyz(VERSION))
    return _CACHE["pyz"][1]


def server_url(request: Request) -> str:
    """This server's URL as the client reached it (honours a reverse proxy)."""

    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = (
        request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    )
    url = f"{scheme}://{host}".rstrip("/")
    # Never echo anything unexpected into the generated scripts.
    return url if re.match(r"^https?://[A-Za-z0-9.\-\[\]:]+$", url) else ""


@router.get("")
def cli_info(request: Request) -> Dict[str, Any]:
    url = server_url(request)
    return {
        "version": VERSION,
        "server": url,
        "requires": "Python 3.9 or newer",
        "downloads": {
            "pyz": f"{url}/api/cli/ent.pyz",
            "install_sh": f"{url}/api/cli/install.sh",
            "install_ps1": f"{url}/api/cli/install.ps1",
        },
        "install": {
            "posix": f"curl -fsSL {url}/api/cli/install.sh | sh",
            "windows": f"irm {url}/api/cli/install.ps1 | iex",
        },
        "login": f"ent login {url}",
    }


@router.get("/ent.pyz")
def download_pyz() -> Response:
    return Response(
        _pyz(),
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="ent.pyz"',
            "Cache-Control": "no-cache",
        },
    )


INSTALL_SH = r"""#!/bin/sh
# Install the Entropy command line (ent) from __SERVER__.
#   curl -fsSL __SERVER__/api/cli/install.sh | sh
# Options (environment): ENT_INSTALL_DIR (default ~/.local/bin), ENT_NAME
# (default ent), ENT_INSECURE=1 to skip TLS verification of the download.
set -eu
SERVER="__SERVER__"
BIN_DIR="${ENT_INSTALL_DIR:-$HOME/.local/bin}"
NAME="${ENT_NAME:-ent}"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/entropy-cli"
MARKER="entropy-cli wrapper"

say() { printf '%s\n' "$*"; }
fail() { printf 'ent install: %s\n' "$*" >&2; exit 1; }

PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3.9 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 \
     && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
    PYTHON=$(command -v "$candidate"); break
  fi
done
[ -n "$PYTHON" ] || fail "Python 3.9 or newer is required; install it and run this again."

TARGET="$BIN_DIR/$NAME"
if [ -e "$TARGET" ] && ! grep -q "$MARKER" "$TARGET" 2>/dev/null; then
  fail "$TARGET exists and is not the remote ent client (on an Entropy server it is the local CLI). Choose another name, e.g. ENT_NAME=entr"
fi

mkdir -p "$BIN_DIR" "$DATA_DIR"
TMP="$DATA_DIR/ent.pyz.part"
if command -v curl >/dev/null 2>&1; then
  K=""; [ "${ENT_INSECURE:-0}" = 1 ] && K="-k"
  curl -fsSL $K "$SERVER/api/cli/ent.pyz" -o "$TMP" || fail "download failed"
elif command -v wget >/dev/null 2>&1; then
  K=""; [ "${ENT_INSECURE:-0}" = 1 ] && K="--no-check-certificate"
  wget -q $K -O "$TMP" "$SERVER/api/cli/ent.pyz" || fail "download failed"
else
  "$PYTHON" -c 'import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])' \
    "$SERVER/api/cli/ent.pyz" "$TMP" || fail "download failed"
fi
mv "$TMP" "$DATA_DIR/ent.pyz"

cat > "$TARGET" <<EOF
#!/bin/sh
# $MARKER: Entropy command line for remote servers.
exec "$PYTHON" "$DATA_DIR/ent.pyz" "\$@"
EOF
chmod 755 "$TARGET"

say "Installed $TARGET ($("$TARGET" --version 2>/dev/null | head -n 1))."
case ":$PATH:" in *":$BIN_DIR:"*) ;; *) say "Add $BIN_DIR to your PATH." ;; esac
say "Next: $NAME login $SERVER"
"""

INSTALL_PS1 = r"""# Install the Entropy command line (ent) from __SERVER__.
#   irm __SERVER__/api/cli/install.ps1 | iex
$ErrorActionPreference = 'Stop'
$Server = '__SERVER__'
$Dir = Join-Path $env:LOCALAPPDATA 'entropy-cli'
New-Item -ItemType Directory -Force -Path $Dir | Out-Null

$Python = $null
foreach ($candidate in @('py -3', 'python', 'python3')) {
  try {
    $parts = $candidate.Split(' ')
    $exe = $parts[0]; $rest = $parts[1..($parts.Length)]
    & $exe @rest -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) { $Python = $candidate; break }
  } catch {}
}
if (-not $Python) { throw 'Python 3.9 or newer is required (https://www.python.org/downloads/).' }

Invoke-WebRequest -UseBasicParsing -Uri "$Server/api/cli/ent.pyz" -OutFile (Join-Path $Dir 'ent.pyz')
Set-Content -Encoding ASCII -Path (Join-Path $Dir 'ent.cmd') -Value "@$Python `"%~dp0ent.pyz`" %*"

$UserPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if (-not ($UserPath -split ';' | Where-Object { $_ -eq $Dir })) {
  [Environment]::SetEnvironmentVariable('Path', "$UserPath;$Dir", 'User')
  Write-Host "Added $Dir to your PATH (open a new terminal)."
}
Write-Host "Installed $(Join-Path $Dir 'ent.cmd'). Next: ent login $Server"
"""


@router.get("/install.sh", response_class=PlainTextResponse)
def install_sh(request: Request) -> PlainTextResponse:
    return PlainTextResponse(
        INSTALL_SH.replace("__SERVER__", server_url(request)),
        media_type="text/x-shellscript",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/install.ps1", response_class=PlainTextResponse)
def install_ps1(request: Request) -> PlainTextResponse:
    return PlainTextResponse(
        INSTALL_PS1.replace("__SERVER__", server_url(request)),
        headers={"Cache-Control": "no-cache"},
    )
