"""
Collection exchange: EagleAPI's own format, Postman (v2.0 / v2.1),
SoapUI projects (REST and SOAP) and Insomnia (v4) exports.

Everything goes through one neutral tree:

    {"kind": "folder", "name": str, "children": [node, ...]}
    {"kind": "request", "name": str, "data": <request definition>}

Values are never exported: vault references stay references. In other
tools they become that tool's variables (`${entv:ns/KEY}` <-> `{{KEY}}` in
Postman and Insomnia, `${#Project#KEY}` in SoapUI) and a path without a host
uses the environment's base URL (`{{baseUrl}}`).

"Preserve settings" keeps each request's auth, TLS, polling and options
(and, in EagleAPI's format, the project's TLS profiles); without it only
method, URL, parameters, headers and body travel.
"""

from __future__ import annotations

import json
import re
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qsl, urlsplit

from lib.tools.eagleapi.store import (
    MAX_NAME,
    default_request,
    normalize_request,
    normalize_settings,
)

FORMAT = "entropy-eagleapi"
VERSION = 1
FORMATS = ("eagleapi", "postman", "soapui", "insomnia")
EXPORT_FORMATS = ("eagleapi", "postman", "soapui")
MAX_IMPORT_BYTES = 20 * 1024 * 1024
MAX_IMPORT_ITEMS = 5000

POSTMAN_SCHEMA = "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
SOAPUI_NS = "http://eviware.com/soapui/config"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
BASE_URL_VARIABLE = "baseUrl"

# ${entv:ns/KEY}, ${entvfile:ns/KEY}; Postman {{KEY}}; Insomnia {{ _.KEY }};
# SoapUI ${#Project#KEY} (also #TestSuite#, #TestCase#, #Env#, #Global#).
VAULT_REF = re.compile(r"\$\{(entv|entvfile):([^/}]+)/((?:\{\{ENV\}\}_)?[^}]+)\}")
CURLY_VAR = re.compile(r"\{\{\s*(?:_\.)?([A-Za-z0-9_.\-]+)\s*\}\}")
SOAPUI_VAR = re.compile(r"\$\{#(?:Project|TestSuite|TestCase|Env|Global)#([^}]+)\}")
LEADING_VAR = re.compile(r"^\s*(\{\{\s*(?:_\.)?[A-Za-z0-9_.\-]+\s*\}\}|\$\{#[A-Za-z]+#[^}]+\})")

BASIC_FIELDS = ("method", "url", "params", "headers", "body")
# SoapUI has no folders: our exports name a resource "folder / sub / request".
FOLDER_SEPARATOR = " / "
GENERIC_REQUEST = re.compile(r"^Request( \d+)?$")


class EagleFormatError(ValueError):
    """The file cannot be read; the message says why."""


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _name(value: Any, fallback: str) -> str:
    cleaned = " ".join(str(value or "").split())[:MAX_NAME]
    return cleaned or fallback


def _row(key: Any, value: Any, enabled: bool = True) -> Dict[str, Any]:
    return {"key": str(key or ""), "value": "" if value is None else str(value), "enabled": enabled}


def _strip(data: Dict[str, Any], preserve: bool) -> Dict[str, Any]:
    """A request definition, with only the basics unless settings are kept."""

    data = normalize_request(data)
    if preserve:
        return data
    plain = default_request()
    for field in BASIC_FIELDS:
        plain[field] = data[field]
    return plain


def count_requests(nodes: Iterable[Dict[str, Any]]) -> Tuple[int, int]:
    """(folders, requests) in a tree."""

    folders = requests = 0
    for node in nodes:
        if node["kind"] == "folder":
            folders += 1
            sub_folders, sub_requests = count_requests(node.get("children") or [])
            folders += sub_folders
            requests += sub_requests
        else:
            requests += 1
    return folders, requests


def _walk(nodes: Iterable[Dict[str, Any]]):
    for node in nodes:
        yield node
        if node["kind"] == "folder":
            yield from _walk(node.get("children") or [])


def is_absolute(url: str) -> bool:
    return bool(re.match(r"^[a-z][a-z0-9+.\-]*://", url.strip(), re.I))


# -- variables between tools ---------------------------------------------


def _plain_key(key: str) -> str:
    """{{ENV}}_KEY is KEY of the chosen environment: other tools' environments do that."""

    return re.sub(r"^\{\{ENV\}\}_", "", key)


def to_curly(text: str) -> str:
    """${entv:ns/KEY} -> {{KEY}} (Postman, Insomnia)."""

    return VAULT_REF.sub(lambda match: "{{" + _plain_key(match.group(3)) + "}}", text or "")


def to_soapui(text: str) -> str:
    """${entv:ns/KEY} -> ${#Project#KEY} (SoapUI property expansion)."""

    return VAULT_REF.sub(lambda match: "${#Project#" + _plain_key(match.group(3)) + "}", text or "")


def from_variables(text: str, namespace: str) -> str:
    """{{KEY}} and ${#Project#KEY} -> ${entv:<namespace>/KEY}; Postman's {{$guid}} etc. stay."""

    def vault(match: re.Match[str]) -> str:
        return "${entv:" + namespace + "/" + match.group(1) + "}"

    text = CURLY_VAR.sub(vault, text or "")
    return SOAPUI_VAR.sub(vault, text)


def referenced_keys(nodes: Iterable[Dict[str, Any]]) -> List[str]:
    """Vault keys the requests refer to (for the other tool's variable list)."""

    found: Dict[str, None] = {}
    for node in _walk(nodes):
        if node["kind"] == "request":
            for match in VAULT_REF.finditer(json.dumps(node["data"])):
                found[_plain_key(match.group(3))] = None
    return sorted(found)


def _split_url(url: str) -> Tuple[str, List[Dict[str, Any]]]:
    """A URL without its query, and the query as rows."""

    if "?" not in url:
        return url, []
    base, _, query = url.partition("?")
    return base, [_row(key, value) for key, value in parse_qsl(query, keep_blank_values=True)]


def _import_url(url: str, namespace: str) -> str:
    """
    A URL from another tool. A leading variable that stands for the host
    ({{baseUrl}}/path) becomes a relative path, sent to the environment's
    base URL; other variables become vault references.
    """

    url = (url or "").strip()
    match = LEADING_VAR.match(url)
    if match:
        rest = url[match.end() :]
        if rest == "" or rest.startswith("/") or rest.startswith("?"):
            return rest or "/"
    return from_variables(url, namespace)


def _export_url(url: str, variable: str) -> str:
    """Relative paths get the base URL variable in front."""

    url = url.strip()
    if is_absolute(url) or url.startswith(("{{", "${")):
        return url
    return variable + (url if url.startswith("/") else "/" + url)


# ----------------------------------------------------------------------
# Detection and import
# ----------------------------------------------------------------------


def detect(raw: bytes) -> Tuple[str, Any]:
    """(format, parsed document) of an uploaded file."""

    if len(raw) > MAX_IMPORT_BYTES:
        raise EagleFormatError("The file is too large (20 MB at most).")
    text = raw.decode("utf-8-sig", errors="replace").strip()
    if text.startswith("<"):
        # Entities are refused outright: SoapUI projects never use them.
        if re.search(r"<!(DOCTYPE|ENTITY)", text[:4096], re.I):
            raise EagleFormatError("XML files with a DOCTYPE are not accepted.")
        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            raise EagleFormatError(f"This XML file cannot be read: {exc}.") from None
        if root.tag == f"{{{SOAPUI_NS}}}soapui-project":
            return "soapui", root
        raise EagleFormatError("This XML file is not a SoapUI project.")
    try:
        document = json.loads(text)
    except ValueError:
        raise EagleFormatError(
            "This file is not an EagleAPI, Postman, Insomnia or SoapUI export."
        ) from None
    if isinstance(document, dict):
        if document.get("format") == FORMAT:
            return "eagleapi", document
        info = document.get("info")
        if isinstance(info, dict) and isinstance(document.get("item"), list):
            return "postman", document
        if isinstance(document.get("collection"), dict):  # Postman API wrapper
            inner = document["collection"]
            if isinstance(inner.get("info"), dict):
                return "postman", inner
        if document.get("_type") == "export" and isinstance(document.get("resources"), list):
            return "insomnia", document
    raise EagleFormatError("This file is not an EagleAPI, Postman, Insomnia or SoapUI export.")


def read(raw: bytes, namespace: str, preserve: bool) -> Dict[str, Any]:
    """
    Parse an export: {"format", "name", "collections": [nodes], "settings"
    (EagleAPI with preserved settings, else None), "warnings": [str]}.
    """

    kind, document = detect(raw)
    warnings: List[str] = []
    settings = None
    if kind == "eagleapi":
        name, nodes, settings = _read_eagle(document, preserve)
    elif kind == "postman":
        name, nodes = _read_postman(document, namespace, preserve, warnings)
    elif kind == "insomnia":
        name, nodes = _read_insomnia(document, namespace, preserve, warnings)
    else:
        name, nodes = _read_soapui(document, namespace, preserve, warnings)
    folders, requests = count_requests(nodes)
    if folders + requests > MAX_IMPORT_ITEMS:
        raise EagleFormatError(f"The file has more than {MAX_IMPORT_ITEMS} folders and requests.")
    return {
        "format": kind,
        "name": name,
        "collections": nodes,
        "settings": settings,
        "folders": folders,
        "requests": requests,
        "warnings": warnings[:20]
        + ([f"… and {len(warnings) - 20} more."] if len(warnings) > 20 else []),
    }


# -- EagleAPI -------------------------------------------------------------


def _eagle_nodes(items: Any, preserve: bool, depth: int = 0) -> List[Dict[str, Any]]:
    if depth > 30 or not isinstance(items, list):
        return []
    nodes = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("kind") == "folder":
            nodes.append(
                {
                    "kind": "folder",
                    "name": _name(item.get("name"), "Folder"),
                    "children": _eagle_nodes(item.get("children"), preserve, depth + 1),
                }
            )
        elif item.get("kind") == "request":
            nodes.append(
                {
                    "kind": "request",
                    "name": _name(item.get("name"), "Request"),
                    "data": _strip(item.get("data") or {}, preserve),
                }
            )
    return nodes


def _read_eagle(document: Dict[str, Any], preserve: bool):
    if int(document.get("version") or 0) > VERSION:
        raise EagleFormatError("This export was made by a newer Entropy.")
    nodes = _eagle_nodes(document.get("collections"), preserve)
    settings = None
    if preserve and isinstance(document.get("settings"), dict):
        try:
            settings = normalize_settings(document["settings"])
        except ValueError as exc:
            raise EagleFormatError(f"The TLS profiles in the file are not valid: {exc}") from None
    return _name(document.get("name"), "EagleAPI"), nodes, settings


# -- Postman -----------------------------------------------------------------


def _kv(entries: Any) -> Dict[str, Any]:
    """Postman's [{key, value}] auth parameter lists as a dict."""

    if isinstance(entries, dict):
        return entries
    found: Dict[str, Any] = {}
    for entry in entries if isinstance(entries, list) else []:
        if isinstance(entry, dict) and "key" in entry:
            found[str(entry["key"])] = entry.get("value")
    return found


def _postman_auth(auth: Any, namespace: str) -> Optional[Dict[str, Any]]:
    """Our auth from Postman's; None when the request inherits its parent's."""

    if not isinstance(auth, dict):
        return None
    kind = auth.get("type")
    convert = lambda value: from_variables(str(value or ""), namespace)  # noqa: E731
    if kind == "noauth":
        return {"type": "none"}
    if kind == "basic":
        values = _kv(auth.get("basic"))
        return {
            "type": "basic",
            "username": convert(values.get("username")),
            "password": convert(values.get("password")),
        }
    if kind == "bearer":
        return {"type": "bearer", "token": convert(_kv(auth.get("bearer")).get("token"))}
    if kind == "oauth2":
        values = _kv(auth.get("oauth2"))
        return {
            "type": "oauth2",
            "token_url": convert(values.get("accessTokenUrl")),
            "client_id": convert(values.get("clientId")),
            "client_secret": convert(values.get("clientSecret")),
            "scope": convert(values.get("scope")),
            "client_auth": "basic" if values.get("client_authentication") == "header" else "body",
        }
    return {"type": "none", "unsupported": str(kind or "")}


def _postman_request(
    item: Dict[str, Any],
    inherited_auth: Optional[Dict[str, Any]],
    namespace: str,
    preserve: bool,
    warnings: List[str],
) -> Dict[str, Any]:
    request = item.get("request")
    if isinstance(request, str):
        request = {"url": request, "method": "GET"}
    request = request if isinstance(request, dict) else {}
    name = _name(item.get("name"), "Request")
    convert = lambda value: from_variables(str(value or ""), namespace)  # noqa: E731

    url = request.get("url")
    params: List[Dict[str, Any]] = []
    if isinstance(url, dict):
        raw_url = str(url.get("raw") or "")
        query = url.get("query")
        base, _ = _split_url(raw_url)
        if isinstance(query, list):
            params = [
                _row(entry.get("key"), convert(entry.get("value")), not entry.get("disabled"))
                for entry in query
                if isinstance(entry, dict)
            ]
        else:
            base, params = _split_url(raw_url)
    else:
        base, params = _split_url(str(url or ""))
        params = [{**row, "value": convert(row["value"])} for row in params]

    headers = [
        _row(header.get("key"), convert(header.get("value")), not header.get("disabled"))
        for header in request.get("header") or []
        if isinstance(header, dict)
    ]

    body: Dict[str, Any] = {"mode": "none"}
    source = request.get("body") if isinstance(request.get("body"), dict) else {}
    mode = source.get("mode")
    if mode == "raw":
        language = ((source.get("options") or {}).get("raw") or {}).get("language")
        text = convert(source.get("raw"))
        content_type = next(
            (row["value"] for row in headers if row["key"].lower() == "content-type"), ""
        )
        if language == "json" or "json" in content_type.lower():
            body = {"mode": "json", "json": text}
        else:
            body = {"mode": "raw", "raw": text, "content_type": content_type or "text/plain"}
    elif mode in ("urlencoded", "formdata"):
        rows = []
        for entry in source.get(mode) or []:
            if not isinstance(entry, dict):
                continue
            if entry.get("type") == "file":
                warnings.append(f"{name}: file field '{entry.get('key')}' was left out.")
                continue
            rows.append(
                _row(entry.get("key"), convert(entry.get("value")), not entry.get("disabled"))
            )
        body = {"mode": "form", "form": rows}
        if mode == "formdata":
            warnings.append(f"{name}: multipart form data is sent URL-encoded.")
    elif mode == "graphql":
        graphql = source.get("graphql") or {}
        variables = graphql.get("variables") or "{}"
        try:
            variables = json.loads(variables) if isinstance(variables, str) else variables
        except ValueError:
            variables = {}
        body = {
            "mode": "json",
            "json": json.dumps(
                {"query": graphql.get("query") or "", "variables": variables}, indent=2
            ),
        }
    elif mode == "file":
        warnings.append(f"{name}: a file body was left out.")

    auth = _postman_auth(request.get("auth"), namespace) if "auth" in request else None
    if auth is None:
        auth = inherited_auth
    if auth and auth.get("unsupported"):
        warnings.append(f"{name}: Postman auth '{auth['unsupported']}' is not supported.")
    if item.get("event"):
        warnings.append(f"{name}: scripts were left out.")

    data = {
        "method": str(request.get("method") or "GET"),
        "url": _import_url(base, namespace),
        "params": params,
        "headers": headers,
        "body": body,
    }
    if preserve and auth:
        data["auth"] = {key: value for key, value in auth.items() if key != "unsupported"}
    return normalize_request(data)


def _postman_items(
    items: Any,
    inherited_auth: Optional[Dict[str, Any]],
    namespace: str,
    preserve: bool,
    warnings: List[str],
    depth: int = 0,
) -> List[Dict[str, Any]]:
    if depth > 30 or not isinstance(items, list):
        return []
    nodes = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if isinstance(item.get("item"), list):
            auth = _postman_auth(item.get("auth"), namespace) or inherited_auth
            nodes.append(
                {
                    "kind": "folder",
                    "name": _name(item.get("name"), "Folder"),
                    "children": _postman_items(
                        item["item"], auth, namespace, preserve, warnings, depth + 1
                    ),
                }
            )
        else:
            nodes.append(
                {
                    "kind": "request",
                    "name": _name(item.get("name"), "Request"),
                    "data": _postman_request(item, inherited_auth, namespace, preserve, warnings),
                }
            )
    return nodes


def _read_postman(document: Dict[str, Any], namespace: str, preserve: bool, warnings: List[str]):
    info = document.get("info") or {}
    name = _name(info.get("name"), "Postman collection")
    auth = _postman_auth(document.get("auth"), namespace)
    children = _postman_items(document.get("item"), auth, namespace, preserve, warnings)
    if document.get("event"):
        warnings.append("Collection scripts were left out.")
    return name, [{"kind": "folder", "name": name, "children": children}]


# -- Insomnia ----------------------------------------------------------------


def _read_insomnia(document: Dict[str, Any], namespace: str, preserve: bool, warnings: List[str]):
    resources = [entry for entry in document["resources"] if isinstance(entry, dict)]
    convert = lambda value: from_variables(str(value or ""), namespace)  # noqa: E731
    children: Dict[str, List[Dict[str, Any]]] = {}
    for entry in resources:
        children.setdefault(str(entry.get("parentId") or ""), []).append(entry)
    workspaces = [entry for entry in resources if entry.get("_type") == "workspace"]

    def request_node(entry: Dict[str, Any]) -> Dict[str, Any]:
        name = _name(entry.get("name"), "Request")
        base, query = _split_url(str(entry.get("url") or ""))
        params = query + [
            _row(param.get("name"), convert(param.get("value")), not param.get("disabled"))
            for param in entry.get("parameters") or []
            if isinstance(param, dict)
        ]
        headers = [
            _row(header.get("name"), convert(header.get("value")), not header.get("disabled"))
            for header in entry.get("headers") or []
            if isinstance(header, dict)
        ]
        source = entry.get("body") if isinstance(entry.get("body"), dict) else {}
        mime = str(source.get("mimeType") or "")
        body: Dict[str, Any] = {"mode": "none"}
        if "json" in mime:
            body = {"mode": "json", "json": convert(source.get("text"))}
        elif mime in ("application/x-www-form-urlencoded", "multipart/form-data"):
            body = {
                "mode": "form",
                "form": [
                    _row(param.get("name"), convert(param.get("value")), not param.get("disabled"))
                    for param in source.get("params") or []
                    if isinstance(param, dict) and param.get("type") != "file"
                ],
            }
        elif source.get("text"):
            body = {
                "mode": "raw",
                "raw": convert(source.get("text")),
                "content_type": mime or "text/plain",
            }
        auth_source = (
            entry.get("authentication") if isinstance(entry.get("authentication"), dict) else {}
        )
        kind = auth_source.get("type")
        auth: Optional[Dict[str, Any]] = None
        if kind == "basic":
            auth = {
                "type": "basic",
                "username": convert(auth_source.get("username")),
                "password": convert(auth_source.get("password")),
            }
        elif kind == "bearer":
            auth = {"type": "bearer", "token": convert(auth_source.get("token"))}
        elif kind == "oauth2":
            auth = {
                "type": "oauth2",
                "token_url": convert(auth_source.get("accessTokenUrl")),
                "client_id": convert(auth_source.get("clientId")),
                "client_secret": convert(auth_source.get("clientSecret")),
                "scope": convert(auth_source.get("scope")),
            }
        elif kind:
            warnings.append(f"{name}: Insomnia auth '{kind}' is not supported.")
        data = {
            "method": str(entry.get("method") or "GET"),
            "url": _import_url(base, namespace),
            "params": params,
            "headers": headers,
            "body": body,
        }
        if preserve and auth:
            data["auth"] = auth
        return {"kind": "request", "name": name, "data": normalize_request(data)}

    def nodes_under(parent: str, depth: int = 0) -> List[Dict[str, Any]]:
        if depth > 30:
            return []
        found = []
        for entry in sorted(children.get(parent, []), key=lambda e: e.get("metaSortKey") or 0):
            if entry.get("_type") == "request_group":
                found.append(
                    {
                        "kind": "folder",
                        "name": _name(entry.get("name"), "Folder"),
                        "children": nodes_under(str(entry.get("_id")), depth + 1),
                    }
                )
            elif entry.get("_type") == "request":
                found.append(request_node(entry))
            elif entry.get("_type") in ("grpc_request", "websocket_request"):
                warnings.append(f"{entry.get('name')}: {entry['_type']} is not supported.")
        return found

    collections = []
    for workspace in workspaces or [{"_id": "", "name": "Insomnia"}]:
        collections.append(
            {
                "kind": "folder",
                "name": _name(workspace.get("name"), "Insomnia"),
                "children": nodes_under(str(workspace.get("_id") or "")),
            }
        )
    name = collections[0]["name"] if len(collections) == 1 else "Insomnia"
    return name, collections


# -- SoapUI ------------------------------------------------------------------


def _q(tag: str) -> str:
    return f"{{{SOAPUI_NS}}}{tag}"


def _text_of(element: Optional[ET.Element]) -> str:
    return (element.text or "") if element is not None else ""


def _soapui_headers(request: ET.Element, namespace: str) -> List[Dict[str, Any]]:
    """Headers live in an escaped XML fragment inside a request setting."""

    headers: List[Dict[str, Any]] = []
    for setting in request.iter(_q("setting")):
        if not str(setting.get("id") or "").endswith("@request-headers") or not setting.text:
            continue
        fragment = setting.text.strip()
        if re.search(r"<!(DOCTYPE|ENTITY)", fragment, re.I):
            continue
        try:
            root = ET.fromstring(fragment)
        except ET.ParseError:
            continue
        for entry in root.iter():
            if entry.tag.endswith("entry") and entry.get("key"):
                headers.append(
                    _row(entry.get("key"), from_variables(entry.get("value") or "", namespace))
                )
    return headers


def _soapui_credentials(request: ET.Element, namespace: str) -> Optional[Dict[str, Any]]:
    credentials = request.find(_q("credentials"))
    if credentials is None:
        return None
    username = _text_of(credentials.find(_q("username")))
    if not username:
        return None
    return {
        "type": "basic",
        "username": from_variables(username, namespace),
        "password": from_variables(_text_of(credentials.find(_q("password"))), namespace),
    }


def _soapui_entries(request: ET.Element) -> Dict[str, str]:
    """A REST request's parameter values (<con:parameters><entry key value/>)."""

    values: Dict[str, str] = {}
    parameters = request.find(_q("parameters"))
    if parameters is not None:
        for entry in parameters:
            if entry.tag.endswith("entry") and entry.get("key") is not None:
                values[str(entry.get("key"))] = entry.get("value") or ""
    return values


def _soapui_definitions(element: ET.Element) -> List[Tuple[str, str, str]]:
    """(name, style, default) of a resource's or method's parameters."""

    found = []
    parameters = element.find(_q("parameters"))
    if parameters is None:
        return found
    for parameter in parameters.findall(_q("parameter")):
        found.append(
            (
                _text_of(parameter.find(_q("name"))),
                _text_of(parameter.find(_q("style"))).upper() or "QUERY",
                _text_of(parameter.find(_q("default"))) or _text_of(parameter.find(_q("value"))),
            )
        )
    return found


def _join(base: str, path: str) -> str:
    if not path:
        return base
    if not base:
        return path
    return base.rstrip("/") + "/" + path.lstrip("/")


def _read_soapui(root: ET.Element, namespace: str, preserve: bool, warnings: List[str]):
    project_name = _name(root.get("name"), "SoapUI project")
    collections = []
    convert = lambda value: from_variables(value or "", namespace)  # noqa: E731

    for interface in root.findall(_q("interface")):
        kind = interface.get(f"{{{XSI_NS}}}type") or ""
        interface_name = _name(interface.get("name"), "Interface")
        endpoints = [_text_of(e) for e in interface.findall(f"{_q('endpoints')}/{_q('endpoint')}")]
        children: List[Dict[str, Any]] = []

        if kind.endswith("RestService"):
            base_path = interface.get("basePath") or ""

            def resources(
                element: ET.Element,
                prefix: str,
                inherited: List[Tuple[str, str, str]],
                depth: int = 0,
                endpoints: List[str] = endpoints,
            ):
                nodes = []
                if depth > 30:
                    return nodes
                for resource in element.findall(_q("resource")):
                    path = _join(prefix, resource.get("path") or "")
                    definitions = inherited + _soapui_definitions(resource)
                    folder = {
                        "kind": "folder",
                        "name": _name(resource.get("name"), path or "Resource"),
                        "children": [],
                    }
                    for method in resource.findall(_q("method")):
                        method_definitions = definitions + _soapui_definitions(method)
                        for request in method.findall(_q("request")):
                            folder["children"].append(
                                _soapui_rest_request(
                                    request,
                                    method,
                                    path,
                                    method_definitions,
                                    endpoints,
                                    preserve,
                                    namespace,
                                    convert,
                                )
                            )
                    folder["children"].extend(resources(resource, path, definitions, depth + 1))
                    nodes.append(folder)
                return nodes

            children = _soapui_folders(resources(interface, base_path, []))
        elif kind.endswith("WsdlInterface"):
            soap12 = interface.get("soapVersion") == "1_2"
            for operation in interface.findall(_q("operation")):
                action = operation.get("action") or ""
                folder = {
                    "kind": "folder",
                    "name": _name(operation.get("name"), "Operation"),
                    "children": [],
                }
                for call in operation.findall(_q("call")):
                    endpoint = _text_of(call.find(_q("endpoint"))) or (
                        endpoints[0] if endpoints else ""
                    )
                    content_type = (
                        "application/soap+xml; charset=utf-8"
                        if soap12
                        else "text/xml; charset=utf-8"
                    )
                    if soap12 and action:
                        content_type += f'; action="{action}"'
                    headers = _soapui_headers(call, namespace)
                    if action and not soap12:
                        headers.insert(0, _row("SOAPAction", f'"{action}"'))
                    data: Dict[str, Any] = {
                        "method": "POST",
                        "url": convert(endpoint),
                        "headers": headers,
                        "body": {
                            "mode": "raw",
                            "raw": convert(_text_of(call.find(_q("request")))),
                            "content_type": content_type,
                        },
                    }
                    auth = _soapui_credentials(call, namespace)
                    if preserve and auth:
                        data["auth"] = auth
                    folder["children"].append(
                        {
                            "kind": "request",
                            "name": _name(call.get("name"), "Request"),
                            "data": normalize_request(data),
                        }
                    )
                children.append(folder)
        else:
            warnings.append(f"{interface_name}: interface type '{kind}' is not supported.")
            continue
        collections.append({"kind": "folder", "name": interface_name, "children": children})

    if root.find(_q("testSuite")) is not None:
        warnings.append("Test suites were left out; their requests are in the interfaces.")
    if not collections:
        raise EagleFormatError("The SoapUI project has no REST or SOAP interfaces.")
    return project_name, collections


def _soapui_folders(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    A resource with one request becomes that request (named after the
    resource when the request has a generic name); "a / b / c" resource
    names (our own exports) become folders again.
    """

    result: List[Dict[str, Any]] = []

    def place(path: List[str], node: Dict[str, Any]) -> None:
        level = result
        for name in path:
            folder = next(
                (
                    n
                    for n in level
                    if n["kind"] == "folder" and n["name"] == name and n.get("_rebuilt")
                ),
                None,
            )
            if folder is None:
                folder = {"kind": "folder", "name": name, "children": [], "_rebuilt": True}
                level.append(folder)
            level = folder["children"]
        level.append(node)

    for node in nodes:
        if node["kind"] == "request":
            result.append(node)
            continue
        children = _soapui_folders(node["children"])
        requests = [child for child in children if child["kind"] == "request"]
        parts = [part for part in node["name"].split(FOLDER_SEPARATOR) if part]
        if len(children) == 1 and requests:
            request = requests[0]
            if GENERIC_REQUEST.match(request["name"]):
                request = {
                    **request,
                    "name": _name(
                        f"{request['data']['method']} {parts[-1] if parts else node['name']}",
                        "Request",
                    ),
                }
            place(parts[:-1], request)
        else:
            place(
                parts[:-1],
                {**node, "name": parts[-1] if parts else node["name"], "children": children},
            )

    def clean(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for node in nodes:
            node.pop("_rebuilt", None)
            if node["kind"] == "folder":
                clean(node["children"])
        return nodes

    return clean(result)


def _soapui_rest_request(
    request: ET.Element,
    method: ET.Element,
    path: str,
    definitions: List[Tuple[str, str, str]],
    endpoints: List[str],
    preserve: bool,
    namespace: str,
    convert: Any,
) -> Dict[str, Any]:
    values = _soapui_entries(request)
    params: List[Dict[str, Any]] = []
    headers = _soapui_headers(request, namespace)
    for name, style, default in definitions:
        if not name:
            continue
        value = convert(values.get(name, default))
        if style == "TEMPLATE":
            path = path.replace("{" + name + "}", value)
        elif style == "HEADER":
            headers.append(_row(name, value))
        elif style in ("QUERY", "MATRIX", "PLAIN"):
            params.append(_row(name, value))
    endpoint = _text_of(request.find(_q("endpoint"))) or (endpoints[0] if endpoints else "")
    url = _join(convert(endpoint), path) if endpoint else path
    if not endpoint or LEADING_VAR.match(endpoint or ""):
        url = _import_url(_join(endpoint, path), namespace)
    media_type = request.get("mediaType") or "application/json"
    body_text = _text_of(request.find(_q("request")))
    body: Dict[str, Any] = {"mode": "none"}
    verb = (method.get("method") or "GET").upper()
    if body_text and verb not in ("GET", "HEAD"):
        if "json" in media_type:
            body = {"mode": "json", "json": convert(body_text)}
        else:
            body = {"mode": "raw", "raw": convert(body_text), "content_type": media_type}
    data: Dict[str, Any] = {
        "method": verb,
        "url": url,
        "params": params,
        "headers": headers,
        "body": body,
    }
    auth = _soapui_credentials(request, namespace)
    if preserve and auth:
        data["auth"] = auth
    return {
        "kind": "request",
        "name": _name(request.get("name"), "Request"),
        "data": normalize_request(data),
    }


# ----------------------------------------------------------------------
# Export
# ----------------------------------------------------------------------


def export(
    kind: str,
    nodes: List[Dict[str, Any]],
    *,
    name: str,
    preserve: bool,
    settings: Optional[Dict[str, Any]] = None,
    project: str = "",
    exported_by: str = "",
) -> Tuple[bytes, str, str]:
    """(content, media type, file extension) of collections in a format."""

    nodes = [_stripped(node, preserve) for node in nodes]
    if kind == "eagleapi":
        document: Dict[str, Any] = {
            "format": FORMAT,
            "version": VERSION,
            "name": name,
            "project": project,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "exported_by": exported_by,
            "preserve": preserve,
            "collections": nodes,
        }
        if preserve and settings is not None:
            document["settings"] = _used_settings(nodes, settings)
        return (
            json.dumps(document, indent=2, ensure_ascii=False).encode("utf-8"),
            "application/json",
            "eagleapi.json",
        )
    if kind == "postman":
        return (
            json.dumps(_postman(nodes, name, preserve), indent=2, ensure_ascii=False).encode(
                "utf-8"
            ),
            "application/json",
            "postman_collection.json",
        )
    if kind == "soapui":
        return _soapui(nodes, name, preserve), "application/xml", "soapui-project.xml"
    raise EagleFormatError(f"Unknown export format '{kind}'.")


def _stripped(node: Dict[str, Any], preserve: bool) -> Dict[str, Any]:
    if node["kind"] == "folder":
        return {
            "kind": "folder",
            "name": node["name"],
            "children": [_stripped(child, preserve) for child in node.get("children") or []],
        }
    return {
        "kind": "request",
        "name": node["name"],
        "data": _strip(node.get("data") or {}, preserve),
    }


def _used_settings(nodes: List[Dict[str, Any]], settings: Dict[str, Any]) -> Dict[str, Any]:
    """All TLS profiles (they are small and requests may inherit the default)."""

    return {
        "tls_profiles": settings.get("tls_profiles") or [],
        "default_tls": settings.get("default_tls") or "",
    }


# -- Postman -----------------------------------------------------------------


def _postman_auth_out(auth: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    kind = auth.get("type")
    pair = lambda key, value: {"key": key, "value": to_curly(value), "type": "string"}  # noqa: E731
    if kind == "basic":
        return {
            "type": "basic",
            "basic": [pair("username", auth["username"]), pair("password", auth["password"])],
        }
    if kind == "bearer":
        return {"type": "bearer", "bearer": [pair("token", auth["token"])]}
    if kind == "oauth2":
        return {
            "type": "oauth2",
            "oauth2": [
                pair("grant_type", "client_credentials"),
                pair("accessTokenUrl", auth["token_url"]),
                pair("clientId", auth["client_id"]),
                pair("clientSecret", auth["client_secret"]),
                pair("scope", auth["scope"]),
                pair(
                    "client_authentication",
                    "header" if auth.get("client_auth") == "basic" else "body",
                ),
            ],
        }
    return None


def _postman_item(node: Dict[str, Any], preserve: bool) -> Dict[str, Any]:
    if node["kind"] == "folder":
        return {
            "name": node["name"],
            "item": [_postman_item(child, preserve) for child in node["children"]],
        }
    data = node["data"]
    base, query_rows = _split_url(data["url"])
    data = {**data, "params": query_rows + data["params"]}
    raw = to_curly(_export_url(base, "{{" + BASE_URL_VARIABLE + "}}"))
    query = [
        {
            "key": row["key"],
            "value": to_curly(row["value"]),
            **({"disabled": True} if not row["enabled"] else {}),
        }
        for row in data["params"]
    ]
    enabled = [f"{row['key']}={to_curly(row['value'])}" for row in data["params"] if row["enabled"]]
    request: Dict[str, Any] = {
        "method": data["method"],
        "header": [
            {
                "key": row["key"],
                "value": to_curly(row["value"]),
                **({"disabled": True} if not row["enabled"] else {}),
            }
            for row in data["headers"]
        ],
        "url": {
            "raw": raw + ("?" + "&".join(enabled) if enabled else ""),
            **({"query": query} if query else {}),
        },
    }
    body = data["body"]
    if body["mode"] == "json":
        request["body"] = {
            "mode": "raw",
            "raw": to_curly(body["json"]),
            "options": {"raw": {"language": "json"}},
        }
    elif body["mode"] == "raw":
        request["body"] = {
            "mode": "raw",
            "raw": to_curly(body["raw"]),
            "options": {"raw": {"language": "text"}},
        }
        if not any(row["key"].lower() == "content-type" for row in data["headers"]):
            request["header"].append({"key": "Content-Type", "value": body["content_type"]})
    elif body["mode"] == "form":
        request["body"] = {
            "mode": "urlencoded",
            "urlencoded": [
                {
                    "key": row["key"],
                    "value": to_curly(row["value"]),
                    **({"disabled": True} if not row["enabled"] else {}),
                }
                for row in body["form"]
            ],
        }
    if preserve:
        auth = _postman_auth_out(data["auth"])
        request["auth"] = auth or {"type": "noauth"}
    return {"name": node["name"], "request": request}


def _postman(nodes: List[Dict[str, Any]], name: str, preserve: bool) -> Dict[str, Any]:
    # One collection: export its content at the top level of the Postman file.
    if len(nodes) == 1 and nodes[0]["kind"] == "folder":
        name, nodes = nodes[0]["name"], nodes[0]["children"]
    keys = referenced_keys(nodes)
    return {
        "info": {"_postman_id": str(uuid.uuid4()), "name": name, "schema": POSTMAN_SCHEMA},
        "item": [_postman_item(node, preserve) for node in nodes],
        "variable": [{"key": BASE_URL_VARIABLE, "value": ""}]
        + [{"key": key, "value": ""} for key in keys if key != BASE_URL_VARIABLE],
    }


# -- SoapUI ------------------------------------------------------------------


def _con(parent: ET.Element, tag: str, text: Optional[str] = None, **attributes: str) -> ET.Element:
    element = ET.SubElement(
        parent, _q(tag), {key: value for key, value in attributes.items() if value is not None}
    )
    if text is not None:
        element.text = text
    return element


def _soapui(nodes: List[Dict[str, Any]], name: str, preserve: bool) -> bytes:
    ET.register_namespace("con", SOAPUI_NS)
    ET.register_namespace("xsi", XSI_NS)
    project = ET.Element(
        _q("soapui-project"),
        {"id": str(uuid.uuid4()), "name": name, "soapui-version": "5.7.0", "resourceRoot": ""},
    )
    _con(project, "settings")

    # Each top-level collection is a REST service; requests outside a folder go in one more.
    loose = [node for node in nodes if node["kind"] == "request"]
    services = [node for node in nodes if node["kind"] == "folder"]
    if loose:
        services.append({"kind": "folder", "name": name, "children": loose})

    for service in services:
        interface = _con(
            project,
            "interface",
            **{
                f"{{{XSI_NS}}}type": "con:RestService",
                "id": str(uuid.uuid4()),
                "name": service["name"],
                "type": "rest",
                "wadlVersion": "http://wadl.dev.java.net/2009/02",
            },
        )
        _con(interface, "settings")
        _con(interface, "definitionCache", type="TEXT", rootPart="")
        endpoints = _con(interface, "endpoints")
        _con(endpoints, "endpoint", "${#Project#" + BASE_URL_VARIABLE + "}")
        for path_names, data in _flatten(service["children"], []):
            _soapui_resource(interface, FOLDER_SEPARATOR.join(path_names), data, preserve)

    properties = _con(project, "properties")
    for key in [BASE_URL_VARIABLE] + [k for k in referenced_keys(nodes) if k != BASE_URL_VARIABLE]:
        prop = _con(properties, "property")
        _con(prop, "name", key)
        _con(prop, "value", "")
    _con(project, "wssContainer")
    _con(project, "oAuth2ProfileContainer")
    _con(project, "oAuth1ProfileContainer")
    tree = ET.tostring(project, encoding="unicode")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n' + tree).encode("utf-8")


def _flatten(nodes: List[Dict[str, Any]], prefix: List[str]):
    """(names along the path, request data) for every request below."""

    for node in nodes:
        if node["kind"] == "folder":
            yield from _flatten(node["children"], prefix + [node["name"]])
        else:
            yield prefix + [node["name"]], node["data"]


def _soapui_resource(
    interface: ET.Element, name: str, data: Dict[str, Any], preserve: bool
) -> None:
    base, query_rows = _split_url(data["url"].strip())
    data = {**data, "params": query_rows + data["params"], "headers": list(data["headers"])}
    if preserve and data["auth"]["type"] == "bearer":
        data["headers"].append(_row("Authorization", "Bearer " + data["auth"]["token"]))
    url = to_soapui(base)
    endpoint = ""
    path = url
    if is_absolute(url):
        parts = urlsplit(url)
        endpoint = f"{parts.scheme}://{parts.netloc}"
        path = parts.path or "/"
    path = path.split("?", 1)[0]
    resource = _con(interface, "resource", name=name, path=path, id=str(uuid.uuid4()))
    _con(resource, "settings")
    _con(resource, "parameters")
    method = _con(
        resource, "method", name=data["method"], method=data["method"], id=str(uuid.uuid4())
    )
    _con(method, "settings")
    definitions = _con(method, "parameters")
    for row in data["params"]:
        if not row["key"]:
            continue
        parameter = _con(definitions, "parameter")
        _con(parameter, "name", row["key"])
        _con(parameter, "value", to_soapui(row["value"]))
        _con(parameter, "style", "QUERY")
        _con(parameter, "default", to_soapui(row["value"]))

    body = data["body"]
    media_type = {"json": "application/json", "form": "application/x-www-form-urlencoded"}.get(
        body["mode"], body.get("content_type") or "application/json"
    )
    request = _con(
        method,
        "request",
        name=name.split(FOLDER_SEPARATOR)[-1],
        mediaType=media_type,
        id=str(uuid.uuid4()),
        postQueryString="false",
    )
    settings = _con(request, "settings")
    headers = [row for row in data["headers"] if row["enabled"] and row["key"]]
    if headers:
        fragment = (
            '<xml-fragment xmlns:con="'
            + SOAPUI_NS
            + '">'
            + "".join(
                '<con:entry key="{}" value="{}"/>'.format(
                    _attr(row["key"]), _attr(to_soapui(row["value"]))
                )
                for row in headers
            )
            + "</xml-fragment>"
        )
        _con(
            settings,
            "setting",
            fragment,
            id="com.eviware.soapui.impl.wsdl.WsdlRequest@request-headers",
        )
    _con(request, "endpoint", endpoint or "${#Project#" + BASE_URL_VARIABLE + "}")
    text = ""
    if body["mode"] == "json":
        text = body["json"]
    elif body["mode"] == "raw":
        text = body["raw"]
    elif body["mode"] == "form":
        text = "&".join(f"{row['key']}={row['value']}" for row in body["form"] if row["enabled"])
    _con(request, "request", to_soapui(text))
    _con(request, "originalUri", path)
    if preserve and data["auth"]["type"] == "basic":
        credentials = _con(request, "credentials")
        _con(credentials, "username", to_soapui(data["auth"]["username"]))
        _con(credentials, "password", to_soapui(data["auth"]["password"]))
        _con(credentials, "selectedAuthProfile", "Basic")
        _con(credentials, "authType", "Global HTTP Settings")
    values = _con(request, "parameters")
    for row in data["params"]:
        if row["key"] and row["enabled"]:
            ET.SubElement(
                values, _q("entry"), {"key": row["key"], "value": to_soapui(row["value"])}
            )


def _attr(value: str) -> str:
    return (
        value.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
    )
