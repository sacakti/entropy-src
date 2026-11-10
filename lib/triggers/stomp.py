"""
Queue triggers: a STOMP client that listens on the destinations of the enabled
queue triggers, on the broker set in Administration -> Settings -> Message queue
(ActiveMQ, or any broker speaking STOMP), and fires the trigger for each message.

It runs in the background process of the main node (the one firing schedules), so
one message starts one run. A message is acknowledged once its run is started or its
failure to start is recorded: a payload a run cannot use is not redelivered forever.
"""

from __future__ import annotations

import contextlib
import json
import logging
import socket
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .store import TriggerStore

LOGGER = logging.getLogger("entropy.triggers")

# How often the triggers and settings are read again, and how long to wait after a
# failure (doubling up to the most).
CHECK_SECONDS = 15
RETRY_SECONDS = 5
RETRY_MOST_SECONDS = 120
# The broker is asked for a heart-beat this often; silence for longer than
# SILENCE_SECONDS means the connection is gone.
HEARTBEAT_MS = 20000
SILENCE_SECONDS = 70
READ_SECONDS = 1.0
MAX_FRAME = 1024 * 1024


class StompError(RuntimeError):
    """The broker refused, sent something that is not STOMP, or went quiet."""


# ----------------------------------------------------------------------
# Frames
# ----------------------------------------------------------------------

_UNESCAPE = {"\\n": "\n", "\\c": ":", "\\\\": "\\", "\\r": "\r"}


def _unescape(value: str) -> str:
    out, index = [], 0
    while index < len(value):
        pair = value[index : index + 2]
        if pair in _UNESCAPE:
            out.append(_UNESCAPE[pair])
            index += 2
        else:
            out.append(value[index])
            index += 1
    return "".join(out)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace(":", "\\c").replace("\r", "\\r")


def frame(command: str, headers: Dict[str, str], body: bytes = b"") -> bytes:
    """One frame to send (headers escaped as STOMP 1.2 asks; CONNECT ones are not)."""

    escape = (lambda text: text) if command == "CONNECT" else _escape
    lines = [command, *(f"{escape(key)}:{escape(value)}" for key, value in headers.items())]
    return ("\n".join(lines) + "\n\n").encode("utf-8") + body + b"\0"


class FrameReader:
    """Frames out of the bytes received; heart-beats (bare newlines) are skipped."""

    def __init__(self) -> None:
        self._buffer = b""

    def feed(self, data: bytes) -> List[Tuple[str, Dict[str, str], bytes]]:
        self._buffer += data
        frames = []
        while True:
            self._buffer = self._buffer.lstrip(b"\r\n")
            parsed = self._next()
            if parsed is None:
                break
            frames.append(parsed)
        if len(self._buffer) > MAX_FRAME:
            raise StompError("The broker sent a frame larger than 1 MB.")
        return frames

    def _next(self) -> Optional[Tuple[str, Dict[str, str], bytes]]:
        end = self._buffer.find(b"\n\n")
        crlf = self._buffer.find(b"\r\n\r\n")
        if crlf != -1 and (end == -1 or crlf < end):
            end, gap = crlf, 4
        else:
            gap = 2
        if end == -1:
            return None
        head = self._buffer[:end].decode("utf-8", "replace").replace("\r\n", "\n")
        command, *lines = head.split("\n")
        headers: Dict[str, str] = {}
        for line in lines:
            key, _, value = line.partition(":")
            # The first of a repeated header counts.
            headers.setdefault(_unescape(key), _unescape(value))
        start = end + gap
        length = headers.get("content-length")
        if length is not None and length.isdigit():
            stop = start + int(length)
            if len(self._buffer) < stop + 1:
                return None
            body = self._buffer[start:stop]
            self._buffer = self._buffer[stop + 1 :]
        else:
            stop = self._buffer.find(b"\0", start)
            if stop == -1:
                return None
            body = self._buffer[start:stop]
            self._buffer = self._buffer[stop + 1 :]
        return command.strip(), headers, body


# ----------------------------------------------------------------------
# Listener
# ----------------------------------------------------------------------


class StompListener:
    """Keeps one STOMP connection subscribed to every enabled queue trigger."""

    def __init__(
        self,
        context: Any,
        stop: threading.Event,
        connect: Optional[Callable[[Dict[str, Any], bool], socket.socket]] = None,
    ) -> None:
        self._context = context
        self._stop = stop
        self._thread: Optional[threading.Thread] = None
        if connect is None:
            from lib.system.connections import _connect

            connect = _connect
        self._connect = connect

    @property
    def _store(self) -> TriggerStore:
        return TriggerStore(self._context.database_manager.connection)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="entropy-triggers", daemon=True)
        self._thread.start()

    def join(self, timeout: float) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    # -- configuration --------------------------------------------------

    def configuration(self) -> Tuple[Optional[Dict[str, Any]], Dict[str, str], str]:
        """(broker settings, subscription id -> destination, why not listening)."""

        from lib.system.settings import settings_for

        triggers = self._store.enabled_queue_triggers()
        if not triggers:
            return None, {}, "No queue trigger is enabled."
        values = settings_for(self._context).values("queue")
        if not values.get("enabled"):
            return None, {}, "The message queue is off (Administration → Settings → Message queue)."
        if values.get("broker") != "activemq":
            return (
                None,
                {},
                "Queue triggers need a STOMP broker: set the message queue to ActiveMQ (STOMP),"
                " or another broker's STOMP port.",
            )
        return values, {f"t{item['id']}": str(item["destination"]) for item in triggers}, ""

    # -- loop -----------------------------------------------------------

    def _loop(self) -> None:
        delay = RETRY_SECONDS
        idle_reason = None
        while not self._stop.is_set():
            try:
                values, subscriptions, reason = self.configuration()
            except Exception as error:  # noqa: BLE001 - kept as the status; tried again
                values, subscriptions, reason = None, {}, f"Unable to read the settings: {error}"
            if values is None:
                if reason != idle_reason:
                    self._status("off", reason)
                    idle_reason = reason
                self._stop.wait(CHECK_SECONDS)
                continue
            idle_reason = None
            try:
                self.session(values, subscriptions)
                delay = RETRY_SECONDS
            except Exception as error:  # noqa: BLE001 - reported, then connect again
                LOGGER.warning("Queue triggers: %s", error)
                self._status("error", f"{error} Trying again in {delay} seconds.")
                self._stop.wait(delay)
                delay = min(delay * 2, RETRY_MOST_SECONDS)

    def _status(self, state: str, detail: str) -> None:
        try:
            self._store.set_listener_status(state, detail)
        except Exception as error:  # noqa: BLE001 - the status is a courtesy
            LOGGER.warning("Unable to record the queue trigger status: %s", error)

    def session(self, values: Dict[str, Any], subscriptions: Dict[str, str]) -> None:
        """Connect, subscribe and fire triggers until the settings change or Entropy stops."""

        target = f"{values['host']}:{values['port']}"
        signature = json.dumps([values, subscriptions], sort_keys=True, default=str)
        sock = self._connect(values, bool(values.get("tls")))
        try:
            sock.settimeout(READ_SECONDS)
            headers = {
                "accept-version": "1.2,1.1,1.0",
                "host": str(values.get("virtual_host") or values["host"]),
                "heart-beat": f"0,{HEARTBEAT_MS}",
            }
            if values.get("username"):
                headers.update(
                    login=str(values["username"]), passcode=str(values.get("password") or "")
                )
            sock.sendall(frame("CONNECT", headers))
            reader = FrameReader()
            version = self._connected(sock, reader, target)
            for subscription, destination in subscriptions.items():
                ack = "client" if version == "1.0" else "client-individual"
                sock.sendall(
                    frame(
                        "SUBSCRIBE",
                        {"id": subscription, "destination": destination, "ack": ack},
                    )
                )
            self._status(
                "listening",
                f"Listening on {len(subscriptions)} destination(s) at {target} (STOMP {version}).",
            )
            heard = checked = time.monotonic()
            while not self._stop.is_set():
                try:
                    data = sock.recv(65536)
                except TimeoutError:
                    data = None
                now = time.monotonic()
                if data == b"":
                    raise StompError(f"{target} closed the connection.")
                if data:
                    heard = now
                    for command, frame_headers, body in reader.feed(data):
                        self._handle(sock, version, command, frame_headers, body)
                elif now - heard > SILENCE_SECONDS:
                    raise StompError(f"{target} sent nothing for {SILENCE_SECONDS} seconds.")
                if now - checked >= CHECK_SECONDS:
                    checked = now
                    current, current_subscriptions, _ = self.configuration()
                    if (
                        current is None
                        or json.dumps([current, current_subscriptions], sort_keys=True, default=str)
                        != signature
                    ):
                        return
        finally:
            # Leaving politely; a connection already gone has nothing to say goodbye to.
            with contextlib.suppress(OSError):
                sock.sendall(frame("DISCONNECT", {}))
            sock.close()

    def _connected(self, sock: socket.socket, reader: FrameReader, target: str) -> str:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                data = sock.recv(65536)
            except TimeoutError:
                continue
            if not data:
                raise StompError(f"{target} closed the connection before it was accepted.")
            for command, headers, body in reader.feed(data):
                if command == "CONNECTED":
                    return headers.get("version", "1.0")
                if command == "ERROR":
                    raise StompError(
                        "The broker refused the connection: "
                        f"{headers.get('message') or body[:200]!r}"
                    )
                raise StompError(f"{target} answered, but not as a STOMP broker.")
        raise StompError(f"{target} did not accept the connection within 10 seconds.")

    def _handle(
        self,
        sock: socket.socket,
        version: str,
        command: str,
        headers: Dict[str, str],
        body: bytes,
    ) -> None:
        if command == "ERROR":
            raise StompError(f"The broker reported: {headers.get('message') or body[:200]!r}")
        if command != "MESSAGE":
            return
        subscription = headers.get("subscription", "")
        message_id = headers.get("message-id", "")
        trigger_id = int(subscription[1:]) if subscription[1:].isdigit() else None
        try:
            self.deliver(trigger_id, headers, body)
        finally:
            sock.sendall(self._ack(version, headers, subscription, message_id))

    @staticmethod
    def _ack(version: str, headers: Dict[str, str], subscription: str, message_id: str) -> bytes:
        if version == "1.2":
            return frame("ACK", {"id": headers.get("ack", message_id)})
        if version == "1.1":
            return frame("ACK", {"subscription": subscription, "message-id": message_id})
        return frame("ACK", {"message-id": message_id})

    def deliver(self, trigger_id: Optional[int], headers: Dict[str, str], body: bytes) -> None:
        """Fire the trigger a message arrived for (a disabled or deleted one is skipped)."""

        from .fire import fire_trigger

        store = self._store
        trigger = store.get(trigger_id) if trigger_id is not None else None
        if trigger is None or not trigger["enabled"] or trigger["source"] != "queue":
            LOGGER.info("Queue triggers: a message for a trigger that is off was dropped.")
            return
        destination = headers.get("destination") or trigger["destination"]
        fire_trigger(
            self._context,
            store,
            trigger,
            payload_text=body.decode("utf-8", "replace"),
            source="queue",
            caller=f"{destination} · message {headers.get('message-id', '?')}",
        )
