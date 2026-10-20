"""
Can a node reach the main node? Address checks, a reachability probe run on
the node over SSH, and plain-language advice for each way it can fail.
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

LOOPBACK_NAMES = {"localhost", "localhost.localdomain", "ip6-localhost"}
ALL_INTERFACES = {"0.0.0.0", "::", ""}


def is_loopback(host: str) -> bool:
    """True for names and addresses that mean "this machine"."""

    host = (host or "").strip().strip("[]").lower()
    if host in LOOPBACK_NAMES or host == "0.0.0.0":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def url_host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


# ----------------------------------------------------------------------
# This server's addresses
# ----------------------------------------------------------------------


def bind_address() -> Tuple[str, int]:
    """Where this web server listens (as configured for `python -m core.web`)."""

    from lib.system import install

    web = install.load()["web"]
    host = os.environ.get("ENTROPY_WEB_HOST") or str(web["host"])
    port = int(os.environ.get("ENTROPY_WEB_PORT") or web["port"])
    return host, port


def _local_addresses() -> List[str]:
    """Non-loopback IPv4 addresses of this machine, primary first."""

    found: List[str] = []
    # The address used to reach the outside world (no packet is sent).
    for target in ("10.255.255.255", "192.0.2.1"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.connect((target, 1))
                found.append(probe.getsockname()[0])
        except OSError:
            continue
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(info[4][0])
    except OSError:
        pass
    return [address for address in dict.fromkeys(found) if not is_loopback(address)]


def server_addresses(scheme: str = "http") -> Dict[str, Any]:
    """How nodes can reach this server, for the node setup dialog."""

    host, port = bind_address()
    # 0.0.0.0 / :: as a listen address means every interface, not loopback.
    local_only = host not in ALL_INTERFACES and is_loopback(host)
    suggestions: List[str] = []
    if not local_only:
        hosts = [host] if host not in ALL_INTERFACES else []
        hosts += _local_addresses()
        name = socket.getfqdn()
        if name and not is_loopback(name) and "." in name:
            hosts.append(name)
        for candidate in dict.fromkeys(hosts):
            shown = f"[{candidate}]" if ":" in candidate else candidate
            suggestions.append(f"{scheme}://{shown}:{port}")
    return {
        "bind_host": host,
        "port": port,
        "local_only": local_only,
        "suggestions": suggestions,
    }


def local_only_advice(host: str, port: int) -> str:
    return (
        f"This Entropy server only listens on {host}:{port}, so other machines cannot "
        "connect to it. Make it listen on the network with "
        f"'ent web config --host 0.0.0.0 --port {port}' and 'ent web restart' "
        "(from a source checkout: start it with ENTROPY_WEB_HOST=0.0.0.0), and allow the "
        "port through the server's firewall."
    )


# ----------------------------------------------------------------------
# Probe from the node
# ----------------------------------------------------------------------

# Prints one line: "ok <status> <body>", or "fail <kind> <detail>", or
# "notool". Uses curl, wget or Python, whichever the node has.
PROBE_SCRIPT = r"""
url="$1"; insecure="$2"
if command -v curl >/dev/null 2>&1; then
  k=""; [ "$insecure" = 1 ] && k="-k"
  body=$(curl -sS $k --connect-timeout 8 --max-time 12 -w '\n%{http_code}' "$url" 2>&1); rc=$?
  if [ $rc -eq 0 ]; then
    code=$(printf '%s' "$body" | tail -n 1); text=$(printf '%s' "$body" | sed '$d' | head -c 300)
    echo "ok $code $text"
  else
    echo "fail curl-$rc $(printf '%s' "$body" | tail -n 1 | head -c 300)"
  fi
  exit 0
fi
for py in python3 python; do
  if command -v "$py" >/dev/null 2>&1; then
    "$py" - "$url" "$insecure" <<'EOF'
import socket, ssl, sys
try:
    from urllib.request import urlopen
    from urllib.error import HTTPError, URLError
except ImportError:
    print("notool"); sys.exit(0)
url, insecure = sys.argv[1], sys.argv[2] == "1"
context = ssl._create_unverified_context() if insecure else None
try:
    response = urlopen(url, timeout=10, context=context)
    print("ok %s %s" % (response.status, response.read(300).decode("utf-8", "replace")))
except HTTPError as error:
    print("ok %s" % error.code)
except URLError as error:
    reason = error.reason
    if isinstance(reason, ssl.SSLError):
        print("fail tls %s" % reason)
    elif isinstance(reason, socket.timeout) or "timed out" in str(reason):
        print("fail timeout %s" % reason)
    elif isinstance(reason, ConnectionRefusedError) or "refused" in str(reason):
        print("fail refused %s" % reason)
    elif isinstance(reason, socket.gaierror):
        print("fail dns %s" % reason)
    else:
        print("fail other %s" % reason)
except socket.timeout as error:
    print("fail timeout %s" % error)
except Exception as error:
    print("fail other %s" % error)
EOF
    exit 0
  fi
done
if command -v wget >/dev/null 2>&1; then
  k=""; [ "$insecure" = 1 ] && k="--no-check-certificate"
  out=$(wget -q -O - -T 10 -t 1 $k "$url" 2>&1); rc=$?
  if [ $rc -eq 0 ]; then echo "ok 200 $(printf '%s' "$out" | head -c 300)"; else echo "fail wget-$rc $out"; fi
  exit 0
fi
echo notool
"""

# curl exit codes worth naming.
_CURL = {6: "dns", 7: "refused", 28: "timeout", 35: "tls", 51: "tls", 58: "tls", 60: "tls"}
# wget exit code 4 is any network failure, 5 TLS.
_WGET = {4: "other", 5: "tls"}


def classify(output: str) -> Tuple[str, str]:
    """(kind, detail) from the probe's output line."""

    line = (output or "").strip().splitlines()[-1] if (output or "").strip() else "notool"
    if line == "notool":
        return "notool", ""
    word, _, rest = line.partition(" ")
    if word == "ok":
        code, _, body = rest.partition(" ")
        if code == "200" and '"entropy"' in body:
            return "ok", ""
        if code.isdigit() and code != "200":
            return "http", f"HTTP {code}"
        return "other-service", body[:200]
    kind, _, detail = rest.partition(" ")
    match = re.match(r"(curl|wget)-(\d+)$", kind)
    if match:
        table = _CURL if match.group(1) == "curl" else _WGET
        kind = table.get(int(match.group(2)), "other")
    if kind == "other":
        lowered = detail.lower()
        for needle, mapped in (
            ("refused", "refused"),
            ("timed out", "timeout"),
            ("name or service", "dns"),
            ("nodename", "dns"),
            ("certificate", "tls"),
            ("ssl", "tls"),
        ):
            if needle in lowered:
                kind = mapped
                break
    return kind, detail.strip()


def classify_log(text: str) -> str:
    """The failure kind from an agent log (urllib error messages)."""

    lowered = (text or "").lower()
    for needle, kind in (
        ("certificate", "tls"),
        ("ssl", "tls"),
        ("connection refused", "refused"),
        ("timed out", "timeout"),
        ("name or service not known", "dns"),
        ("nodename nor servname", "dns"),
        ("temporary failure in name resolution", "dns"),
        ("401", "token"),
        ("403", "token"),
    ):
        if needle in lowered:
            return kind
    return "other"


def advice(
    kind: str, url: str, server: Optional[Dict[str, Any]] = None, node_host: str = ""
) -> str:
    """What went wrong reaching `url` from the node, and what to do about it."""

    host = url_host(url)
    server = server or {}
    # A node on this very machine may use loopback addresses.
    same_machine = is_loopback(node_host)
    local_only = server.get("local_only") and not same_machine
    hint = ""
    if local_only:
        hint = " " + local_only_advice(
            server.get("bind_host", "127.0.0.1"), server.get("port", 8000)
        )
    elif server.get("suggestions"):
        hint = " Addresses of this server: " + ", ".join(server["suggestions"][:3]) + "."

    if is_loopback(host) and not same_machine:
        return (
            f"{url} points at the node itself ('{host}' means \"this machine\" on the node). "
            "Use an address of this Entropy server that the node can reach." + hint
        )
    if kind == "refused":
        return (
            f"The node reached {host}, but nothing accepts connections on that port. "
            "Check the port, and that the Entropy server listens on the network, not only "
            "on 127.0.0.1." + hint
        )
    if kind == "timeout":
        return (
            f"The node got no answer from {url}: a firewall is probably dropping the "
            "connection (on the Entropy server, e.g. macOS firewall or ufw/firewalld, or "
            "between the networks), or the address is not routable from the node." + hint
        )
    if kind == "dns":
        return (
            f"The node cannot resolve '{host}'. Use an IP address or a name the node's DNS knows."
            + hint
        )
    if kind == "tls":
        return (
            f"The TLS connection to {url} failed. Use the certificate's host name, provide "
            "the CA certificate, or turn off TLS verification for a self-signed certificate."
        )
    if kind == "http":
        return f"{url} answered with an error. Check that the URL points at the Entropy web server."
    if kind == "other-service":
        return f"Something answers at {url}, but it is not Entropy. Check the host and port."
    if kind == "token":
        return "The node reached the server but its token was refused. Set the node up again."
    return f"The node could not reach {url}." + hint
