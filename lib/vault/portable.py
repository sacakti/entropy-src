"""
Portable vault exports: secrets leave Entropy only encrypted with a
passphrase the person chooses (scrypt + AES-256-GCM), never with the
installation's own key, so a file can be restored on another Entropy.

File layout (JSON):

    {"format": "entropy-vault", "version": 1,
     "kdf": {"name": "scrypt", "salt": b64, "n": 32768, "r": 8, "p": 1},
     "cipher": "AES-256-GCM", "nonce": b64, "data": b64}

`data` decrypts to {"namespaces": [{"name", "visibility",
"entries": [{"key", "type", "sensitive", "value"}]}], ...}.
"""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

FORMAT = "entropy-vault"
VERSION = 1
MIN_PASSPHRASE = 12
SCRYPT = {"n": 2**15, "r": 8, "p": 1}
AAD = b"entropy-vault-export-v1"
MAX_FILE = 50 * 1024 * 1024


class PortableVaultError(ValueError):
    """The file or passphrase cannot be used; the message says why."""


def _key(passphrase: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

    return Scrypt(salt=salt, length=32, n=n, r=r, p=p).derive(passphrase.encode("utf-8"))


def check_passphrase(passphrase: str) -> None:
    if len(passphrase or "") < MIN_PASSPHRASE:
        raise PortableVaultError(
            f"Use a passphrase of at least {MIN_PASSPHRASE} characters to protect the export."
        )


def seal(payload: Dict[str, Any], passphrase: str) -> bytes:
    """Encrypt a payload with a passphrase."""

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    check_passphrase(passphrase)
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = _key(passphrase, salt, **SCRYPT)
    data = AESGCM(key).encrypt(nonce, json.dumps(payload).encode("utf-8"), AAD)
    envelope = {
        "format": FORMAT,
        "version": VERSION,
        "kdf": {"name": "scrypt", "salt": base64.b64encode(salt).decode(), **SCRYPT},
        "cipher": "AES-256-GCM",
        "nonce": base64.b64encode(nonce).decode(),
        "data": base64.b64encode(data).decode(),
    }
    return json.dumps(envelope, indent=2).encode("utf-8")


def unseal(raw: bytes, passphrase: str) -> Dict[str, Any]:
    """Decrypt an export; a wrong passphrase or a damaged file is refused."""

    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if len(raw) > MAX_FILE:
        raise PortableVaultError("The vault file is too large.")
    try:
        envelope = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise PortableVaultError("This is not an Entropy vault export.") from None
    if not isinstance(envelope, dict) or envelope.get("format") != FORMAT:
        raise PortableVaultError("This is not an Entropy vault export.")
    if envelope.get("version") != VERSION:
        raise PortableVaultError("This vault export was made by a newer Entropy.")
    try:
        kdf = envelope["kdf"]
        n, r, p = int(kdf["n"]), int(kdf["r"]), int(kdf["p"])
        # Bound the work a crafted file can demand.
        if kdf.get("name") != "scrypt" or n > 2**20 or r > 16 or p > 4:
            raise PortableVaultError("The vault export uses unsupported settings.")
        key = _key(passphrase or "", base64.b64decode(kdf["salt"]), n, r, p)
        plain = AESGCM(key).decrypt(
            base64.b64decode(envelope["nonce"]), base64.b64decode(envelope["data"]), AAD
        )
    except InvalidTag:
        raise PortableVaultError("Wrong passphrase, or the file was changed.") from None
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, PortableVaultError):
            raise
        raise PortableVaultError("The vault export is damaged.") from None
    payload = json.loads(plain.decode("utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("namespaces"), list):
        raise PortableVaultError("The vault export is damaged.")
    return payload


# ----------------------------------------------------------------------
# Namespaces <-> payload
# ----------------------------------------------------------------------


def collect(vault_manager: Any, namespaces: List[Any], exported_by: str) -> Dict[str, Any]:
    """Every entry of these namespaces, decrypted, for sealing."""

    items = []
    for namespace in namespaces:
        entries = []
        for entry in vault_manager.list(namespace.id):
            entries.append(
                {
                    "key": entry.key,
                    "type": entry.type.value,
                    "sensitive": bool(entry.sensitive),
                    "value": vault_manager.get(namespace.id, entry.key),
                }
            )
        visibility = getattr(namespace, "visibility", None)
        items.append(
            {
                "name": namespace.name,
                "visibility": getattr(visibility, "value", visibility) or "private",
                "entries": entries,
            }
        )
    return {
        "namespaces": items,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "exported_by": exported_by,
    }


def restore(
    vault_manager: Any,
    namespace_manager: Any,
    payload: Dict[str, Any],
    *,
    owner_user_id: int,
    can_create: bool,
    can_write: Any,
    overwrite: bool,
    only: List[str] = (),
) -> Dict[str, Any]:
    """
    Put the payload's entries into namespaces of the same name: missing
    namespaces are created (owned by the importer) when allowed; existing
    keys are kept unless `overwrite`. `can_write(namespace)` decides whether
    the importer may write to an existing namespace.
    """

    from lib.models.authorization import VaultVisibility
    from lib.models.vault import VaultValueType
    from lib.vault.exceptions import VaultNamespaceNotFoundError

    summary: Dict[str, Any] = {"namespaces": [], "added": 0, "updated": 0, "skipped": 0}
    wanted = set(only)
    for item in payload["namespaces"]:
        name = str(item.get("name") or "").strip()
        if not name or (wanted and name not in wanted):
            continue
        report = {
            "name": name,
            "created": False,
            "added": 0,
            "updated": 0,
            "skipped": 0,
            "error": None,
        }
        try:
            namespace = namespace_manager.get(name)
        except VaultNamespaceNotFoundError:
            namespace = None
        if namespace is None:
            if not can_create:
                report["error"] = "Namespace does not exist and you may not create namespaces."
                summary["namespaces"].append(report)
                continue
            try:
                visibility = VaultVisibility(item.get("visibility") or "private")
            except ValueError:
                visibility = VaultVisibility.PRIVATE
            namespace = namespace_manager.create(
                name=name, owner_user_id=owner_user_id, visibility=visibility
            )
            report["created"] = True
        elif not can_write(namespace):
            report["error"] = "You may not write to this namespace."
            summary["namespaces"].append(report)
            continue

        for entry in item.get("entries") or []:
            key = str(entry.get("key") or "")
            try:
                value_type = VaultValueType(entry.get("type") or "string")
            except ValueError:
                value_type = VaultValueType.STRING
            arguments = dict(
                namespace_id=namespace.id,
                key=key,
                value=entry.get("value"),
                value_type=value_type,
                sensitive=bool(entry.get("sensitive", True)),
            )
            if vault_manager.exists(namespace.id, key):
                if overwrite:
                    vault_manager.update(**arguments)
                    report["updated"] += 1
                else:
                    report["skipped"] += 1
            else:
                vault_manager.add(**arguments)
                report["added"] += 1
        for field in ("added", "updated", "skipped"):
            summary[field] += report[field]
        summary["namespaces"].append(report)
    return summary
