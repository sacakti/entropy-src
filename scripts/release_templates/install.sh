#!/bin/sh
# Entropy installer.
#
#   ./install.sh                         interactive installation
#   ./install.sh --help                  all options
#   ./install.sh uninstall               remove Entropy
#
# Uses the Python bundled in this package. To use another Python 3.9+,
# set ENTROPY_PYTHON=/path/to/python3 or pass --python=/path/to/python3
# (with --deps index or --deps manual when the bundled wheels do not fit it).
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
PYTHON="${ENTROPY_PYTHON:-}"

# Pick out --python=PATH; pass everything else to the installer.
for arg do
    shift
    case "$arg" in
        --python=*) PYTHON="${arg#--python=}" ;;
        *) set -- "$@" "$arg" ;;
    esac
done

if [ -z "$PYTHON" ]; then
    PYTHON="$HERE/python/bin/python3"
    if [ ! -x "$PYTHON" ]; then
        echo "The bundled Python is missing from this package ($PYTHON)." >&2
        exit 1
    fi

    # The bundled Python only runs on the platform it was built for.
    expected=$(sed -n 's/.*"platform": *"\([^"]*\)".*/\1/p' "$HERE/manifest.json")
    case "$(uname -s)-$(uname -m)" in
        Linux-x86_64|Linux-amd64) actual=linux-x86_64 ;;
        Linux-aarch64|Linux-arm64) actual=linux-aarch64 ;;
        Darwin-arm64) actual=macos-arm64 ;;
        Darwin-x86_64) actual=macos-x86_64 ;;
        *) actual="$(uname -s)-$(uname -m)" ;;
    esac
    if [ "$expected" != "$actual" ] && [ -z "${ENTROPY_SKIP_PLATFORM_CHECK:-}" ]; then
        echo "This package is for $expected, but this server is $actual." >&2
        echo "Download the $actual package, or use your own Python with --python=PATH." >&2
        exit 1
    fi
fi

PYTHONPATH="$HERE/application"
export PYTHONPATH
exec "$PYTHON" -s "$HERE/application/lib/install/cli.py" --package-root "$HERE" "$@"
