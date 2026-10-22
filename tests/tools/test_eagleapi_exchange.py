"""EagleAPI: export and import (EagleAPI, Postman, Insomnia, SoapUI), history and access."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterator, List

import pytest

from lib.database.connection import DatabaseConnection
from lib.tools.eagleapi import formats
from lib.tools.eagleapi.access import EagleAccess, EagleAccessError, Viewer
from lib.tools.eagleapi.history import KEEP, EagleHistory, har
from lib.tools.eagleapi.store import EagleStore, normalize_request

NS = "eagleapi-payments"


def _requests(nodes: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {
        node["name"]: node["data"] for node in formats._walk(nodes) if node["kind"] == "request"
    }


def _sample() -> List[Dict[str, Any]]:
    order = normalize_request(
        {
            "method": "POST",
            "url": "/orders?source=web",
            "params": [
                {"key": "q", "value": "${entv:eagleapi-default/{{ENV}}_Q}", "enabled": True}
            ],
            "headers": [
                {"key": "X-Key", "value": "${entv:eagleapi-default/API_KEY}", "enabled": True}
            ],
            "body": {"mode": "json", "json": '{"id": 1}'},
            "auth": {"type": "bearer", "token": "${entv:eagleapi-default/TOKEN}"},
            "tls": {"mode": "profile", "profile": "p1"},
        }
    )
    status = normalize_request({"method": "GET", "url": "https://status.example/health"})
    return [
        {
            "kind": "folder",
            "name": "main",
            "children": [
                {
                    "kind": "folder",
                    "name": "app1",
                    "children": [{"kind": "request", "name": "Order", "data": order}],
                },
                {"kind": "request", "name": "Health", "data": status},
            ],
        }
    ]


SETTINGS = {
    "tls_profiles": [
        {"id": "p1", "name": "Internal CA", "verify": True, "ca_bundle": "${entvfile:x/CA}"}
    ],
    "default_tls": "p1",
}


# ----------------------------------------------------------------------
# Formats
# ----------------------------------------------------------------------


def test_eagleapi_round_trip_keeps_settings_only_when_asked() -> None:
    content, media, extension = formats.export(
        "eagleapi", _sample(), name="main", preserve=True, settings=SETTINGS
    )
    assert media == "application/json" and extension == "eagleapi.json"
    back = formats.read(content, NS, preserve=True)
    assert back["format"] == "eagleapi" and (back["folders"], back["requests"]) == (2, 2)
    order = _requests(back["collections"])["Order"]
    assert order["auth"]["type"] == "bearer" and order["tls"]["mode"] == "profile"
    assert back["settings"]["tls_profiles"][0]["name"] == "Internal CA"
    # The vault reference is kept as is: values never leave the vault.
    assert order["headers"][0]["value"] == "${entv:eagleapi-default/API_KEY}"

    plain, _, _ = formats.export(
        "eagleapi", _sample(), name="main", preserve=False, settings=SETTINGS
    )
    assert "settings" not in json.loads(plain)
    order = _requests(formats.read(plain, NS, preserve=True)["collections"])["Order"]
    assert order["auth"]["type"] == "none" and order["tls"]["mode"] == "inherit"
    assert order["body"]["mode"] == "json"


@pytest.mark.parametrize("kind", ["postman", "soapui"])
def test_other_tools_round_trip(kind: str) -> None:
    content, _, _ = formats.export(kind, _sample(), name="main", preserve=True)
    back = formats.read(content, NS, preserve=True)
    assert back["format"] == kind and not back["warnings"]
    found = _requests(back["collections"])
    order = found["Order"]
    assert order["method"] == "POST" and order["url"] == "/orders"
    params = {row["key"]: row["value"] for row in order["params"]}
    # {{ENV}}_Q is "Q of the chosen environment", which is how other tools see it.
    assert params == {"source": "web", "q": f"${{entv:{NS}/Q}}"}
    headers = {row["key"]: row["value"] for row in order["headers"]}
    assert headers["X-Key"] == f"${{entv:{NS}/API_KEY}}"
    assert order["body"] == {**order["body"], "mode": "json", "json": '{"id": 1}'}
    assert found["Health"]["url"] == "https://status.example/health"
    if kind == "postman":
        assert order["auth"]["token"] == f"${{entv:{NS}/TOKEN}}"
    else:
        assert headers["Authorization"] == f"Bearer ${{entv:{NS}/TOKEN}}"
    # Folders survive (SoapUI has none: resource names carry them).
    main = back["collections"][0]
    assert [child["name"] for child in main["children"]] == ["app1", "Health"]


def test_postman_import() -> None:
    document = {
        "info": {"name": "Shop", "schema": formats.POSTMAN_SCHEMA},
        "auth": {
            "type": "basic",
            "basic": [
                {"key": "username", "value": "{{user}}"},
                {"key": "password", "value": "{{pass}}"},
            ],
        },
        "event": [{"listen": "prerequest", "script": {"exec": ["x"]}}],
        "item": [
            {
                "name": "Orders",
                "item": [
                    {
                        "name": "List",
                        "request": {
                            "method": "GET",
                            "header": [
                                {"key": "Accept", "value": "application/json"},
                                {"key": "X", "value": "1", "disabled": True},
                            ],
                            "url": {
                                "raw": "{{baseUrl}}/orders?page=1",
                                "host": ["{{baseUrl}}"],
                                "query": [{"key": "page", "value": "1"}],
                            },
                        },
                    },
                    {
                        "name": "Create",
                        "request": {
                            "method": "POST",
                            "auth": {"type": "noauth"},
                            "url": "https://api.example/orders",
                            "body": {
                                "mode": "urlencoded",
                                "urlencoded": [{"key": "a", "value": "{{a}}"}],
                            },
                        },
                    },
                    {
                        "name": "GQL",
                        "request": {
                            "method": "POST",
                            "url": "{{host}}/graphql",
                            "body": {"mode": "graphql", "graphql": {"query": "{ me }"}},
                        },
                    },
                ],
            }
        ],
    }
    back = formats.read(json.dumps(document).encode(), NS, preserve=True)
    assert back["format"] == "postman" and back["name"] == "Shop"
    assert back["warnings"] == ["Collection scripts were left out."]
    found = _requests(back["collections"])
    listing = found["List"]
    assert listing["url"] == "/orders" and listing["params"] == [
        {"key": "page", "value": "1", "enabled": True}
    ]
    assert listing["headers"][1]["enabled"] is False
    # Collection auth is inherited by requests without their own.
    assert listing["auth"] == {
        **listing["auth"],
        "type": "basic",
        "username": f"${{entv:{NS}/user}}",
    }
    assert found["Create"]["auth"]["type"] == "none"
    assert found["Create"]["body"]["form"] == [
        {"key": "a", "value": f"${{entv:{NS}/a}}", "enabled": True}
    ]
    assert json.loads(found["GQL"]["body"]["json"])["query"] == "{ me }"
    # Without settings, auth is left behind.
    plain = formats.read(json.dumps(document).encode(), NS, preserve=False)
    assert _requests(plain["collections"])["List"]["auth"]["type"] == "none"


SOAPUI_PROJECT = """<?xml version="1.0" encoding="UTF-8"?>
<con:soapui-project name="Bank" xmlns:con="http://eviware.com/soapui/config">
  <con:interface xsi:type="con:WsdlInterface" name="AccountBinding" soapVersion="1_1"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <con:endpoints><con:endpoint>https://bank.example/ws</con:endpoint></con:endpoints>
    <con:operation name="GetBalance" action="urn:GetBalance">
      <con:call name="Request 1">
        <con:endpoint>https://bank.example/ws</con:endpoint>
        <con:request><![CDATA[<soapenv:Envelope><soapenv:Body><acc>${#Project#ACCOUNT}</acc></soapenv:Body></soapenv:Envelope>]]></con:request>
        <con:credentials><con:username>svc</con:username><con:password>${#Project#PWD}</con:password></con:credentials>
      </con:call>
    </con:operation>
  </con:interface>
  <con:interface xsi:type="con:RestService" name="Rates" basePath="/api"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <con:endpoints><con:endpoint>https://rates.example</con:endpoint></con:endpoints>
    <con:resource name="Rate" path="/rates/{code}">
      <con:parameters>
        <con:parameter><con:name>code</con:name><con:style>TEMPLATE</con:style><con:default>EUR</con:default></con:parameter>
      </con:parameters>
      <con:method name="Get rate" method="GET">
        <con:parameters>
          <con:parameter><con:name>date</con:name><con:style>QUERY</con:style></con:parameter>
        </con:parameters>
        <con:request name="Request 1" mediaType="application/json">
          <con:settings>
            <con:setting id="com.eviware.soapui.impl.wsdl.WsdlRequest@request-headers">
&lt;xml-fragment xmlns:con="http://eviware.com/soapui/config"&gt;
&lt;con:entry key="Accept" value="application/json"/&gt;&lt;/xml-fragment&gt;
</con:setting>
          </con:settings>
          <con:endpoint>https://rates.example</con:endpoint>
          <con:parameters><entry key="date" value="2026-01-01" xmlns="http://eviware.com/soapui/config"/></con:parameters>
        </con:request>
      </con:method>
    </con:resource>
  </con:interface>
  <con:testSuite name="Smoke"/>
</con:soapui-project>"""


def test_soapui_import_rest_and_soap() -> None:
    back = formats.read(SOAPUI_PROJECT.encode(), NS, preserve=True)
    assert back["format"] == "soapui" and back["name"] == "Bank"
    assert [node["name"] for node in back["collections"]] == ["AccountBinding", "Rates"]
    assert back["warnings"] == ["Test suites were left out; their requests are in the interfaces."]
    soap = back["collections"][0]["children"][0]["children"][0]["data"]
    assert soap["method"] == "POST" and soap["url"] == "https://bank.example/ws"
    assert soap["headers"][0] == {"key": "SOAPAction", "value": '"urn:GetBalance"', "enabled": True}
    assert soap["body"]["mode"] == "raw" and f"${{entv:{NS}/ACCOUNT}}" in soap["body"]["raw"]
    assert soap["auth"]["password"] == f"${{entv:{NS}/PWD}}"
    rate = _requests(back["collections"])["GET Rate"]
    assert rate["url"] == "https://rates.example/api/rates/EUR"
    assert rate["params"] == [{"key": "date", "value": "2026-01-01", "enabled": True}]
    assert rate["headers"] == [{"key": "Accept", "value": "application/json", "enabled": True}]


def test_insomnia_import() -> None:
    document = {
        "_type": "export",
        "__export_format": 4,
        "resources": [
            {"_id": "wrk_1", "_type": "workspace", "name": "Payments"},
            {"_id": "fld_1", "_type": "request_group", "parentId": "wrk_1", "name": "v1"},
            {
                "_id": "req_1",
                "_type": "request",
                "parentId": "fld_1",
                "name": "Pay",
                "method": "POST",
                "url": "{{ _.base_url }}/pay",
                "body": {"mimeType": "application/json", "text": '{"amount": {{ _.amount }}}'},
                "headers": [{"name": "X-Id", "value": "1"}],
                "authentication": {"type": "bearer", "token": "{{ _.token }}"},
            },
        ],
    }
    back = formats.read(json.dumps(document).encode(), NS, preserve=True)
    assert back["format"] == "insomnia" and back["collections"][0]["name"] == "Payments"
    pay = _requests(back["collections"])["Pay"]
    assert pay["url"] == "/pay"
    assert pay["body"]["json"] == '{"amount": ${entv:' + NS + '/amount}}'
    assert pay["auth"]["token"] == f"${{entv:{NS}/token}}"


def test_detect_refuses_unknown_and_unsafe_files() -> None:
    for raw, message in [
        (b"hello", "not an EagleAPI"),
        (b'{"a": 1}', "not an EagleAPI"),
        (b"<root/>", "not a SoapUI project"),
        (b'<!DOCTYPE x [<!ENTITY a "b">]><x/>', "DOCTYPE"),
        (json.dumps({"format": "entropy-eagleapi", "version": 99}).encode(), "newer"),
    ]:
        with pytest.raises(formats.EagleFormatError, match=message):
            formats.read(raw, NS, preserve=True)


# ----------------------------------------------------------------------
# Store import, history, access
# ----------------------------------------------------------------------


@pytest.fixture
def connection(tmp_path) -> Iterator[DatabaseConnection]:
    connection = DatabaseConnection(tmp_path / "entropy.db")
    connection.open()
    with connection.transaction():
        connection.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, full_name TEXT)"
        )
        connection.execute("CREATE TABLE groups (id INTEGER PRIMARY KEY, name TEXT)")
        connection.execute("CREATE TABLE user_groups (user_id INTEGER, group_id INTEGER)")
        for user_id, name in [(1, "owner"), (2, "anna"), (3, "bob"), (4, "outsider")]:
            connection.execute("INSERT INTO users VALUES (?, ?, ?)", (user_id, name, name.title()))
        connection.execute("INSERT INTO groups VALUES (1, 'qa')")
        connection.execute("INSERT INTO user_groups VALUES (3, 1)")
    yield connection
    connection.close()


def test_add_tree_and_tree(connection) -> None:
    store = EagleStore(connection)
    store.create(1, kind="folder", name="main")
    created = store.add_tree(1, None, _sample(), "owner")
    # Same name at the same level: the import gets a free one.
    assert store.get(1, created[0])["name"] == "main 2"
    exported = store.tree(1, created)
    assert _requests(exported)["Order"]["method"] == "POST"
    roots = store.roots(1)
    order_id = next(item["id"] for item in store.list(1) if item["name"] == "Order")
    assert roots[order_id]["id"] == created[0] and roots[order_id]["created_by"] == "owner"


def test_history_keeps_masks_and_purges(connection) -> None:
    history = EagleHistory(connection)
    result = {
        "status": 200,
        "elapsed_ms": 12,
        "headers": [["Content-Type", "application/json"]],
        "body": '{"ok": true}',
        "request": {
            "method": "GET",
            "url": "https://x.example/a?b=1",
            "headers": [["Authorization", "••••••"]],
        },
    }
    definition = normalize_request({"url": "/a"})
    first = history.add(
        1,
        7,
        definition=definition,
        result=result,
        item_id=None,
        item_name="A",
        environment="SIT",
        poll=False,
    )
    history.add(
        2,
        7,
        definition=definition,
        result=result,
        item_id=None,
        item_name="B",
        environment=None,
        poll=False,
    )
    history.add(
        1,
        8,
        definition=definition,
        result=result,
        item_id=None,
        item_name="C",
        environment=None,
        poll=False,
    )
    # Per person and per project.
    assert [e["item_name"] for e in history.list(1, 7)["entries"]] == ["A"]
    entry = history.get(1, 7, first)
    assert entry["result"]["request"]["headers"] == [["Authorization", "••••••"]]
    assert history.get(1, 8, first) is None
    document = har(history.entries(1, 7))
    assert document["log"]["entries"][0]["request"]["queryString"] == [{"name": "b", "value": "1"}]
    assert document["log"]["entries"][0]["response"]["status"] == 200
    assert history.purge(1, 7) == 1 and history.list(1, 7)["total"] == 0
    assert history.list(1, 8)["total"] == 1


def test_history_keeps_the_newest(connection) -> None:
    history = EagleHistory(connection)
    for number in range(KEEP + 5):
        history.add(
            1,
            7,
            definition={},
            result={"elapsed_ms": number},
            item_id=None,
            item_name=str(number),
            environment=None,
            poll=False,
        )
    listing = history.list(1, 7, limit=1)
    assert listing["total"] == KEEP and listing["entries"][0]["item_name"] == str(KEEP + 4)


def test_restricted_collection_access(connection) -> None:
    store = EagleStore(connection)
    access = EagleAccess(connection)
    collection = store.create(1, kind="folder", name="secret", user="owner")
    root = store.roots(1)[collection["id"]]
    owner, anna, bob, outsider = (
        Viewer(1, "owner", [], False),
        Viewer(2, "anna", [], False),
        Viewer(3, "bob", [1], False),
        Viewer(4, "outsider", [], False),
    )
    admin = Viewer(9, "admin", [], True)
    # Open: everyone in the project.
    assert access.level(anna, root, access.restricted(1)) == "write"

    members = {"owner", "anna", "bob"}
    access.set(
        1,
        collection["id"],
        restricted=True,
        entries=[
            {"kind": "user", "name": "anna", "level": "read"},
            {"kind": "group", "name": "qa", "level": "write"},
        ],
        allowed_users=members,
        allowed_groups={"qa"},
        updated_by="owner",
    )
    restricted = access.restricted(1)
    assert access.level(owner, root, restricted) == "manage"
    assert access.level(admin, root, restricted) == "manage"
    assert access.level(anna, root, restricted) == "read"
    assert access.level(bob, root, restricted) == "write"
    assert access.level(outsider, root, restricted) is None
    assert [e["name"] for e in access.entries(collection["id"])] == ["anna", "qa"]

    with pytest.raises(EagleAccessError, match="not a member"):
        access.set(
            1,
            collection["id"],
            restricted=True,
            entries=[{"kind": "user", "name": "outsider"}],
            allowed_users=members,
            allowed_groups=set(),
            updated_by="owner",
        )
    access.set(
        1,
        collection["id"],
        restricted=False,
        entries=[],
        allowed_users=members,
        allowed_groups=set(),
        updated_by="owner",
    )
    assert access.level(outsider, root, access.restricted(1)) == "write"
