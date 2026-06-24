#!/usr/bin/env python3

from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import struct
import sys
import urllib.parse


MAX_MESSAGE_SIZE = 16 * 1024 * 1024


def main() -> int:
    url = urllib.parse.urlparse(
        sys.argv[1]
        if len(sys.argv) > 1
        else "ws://127.0.0.1:8765/ws/spectrum"
    )

    if url.scheme != "ws":
        raise SystemExit("Only ws:// URLs are supported by this smoke test")

    host = url.hostname or "127.0.0.1"
    port = url.port or 80
    path = url.path or "/"

    if url.query:
        path = f"{path}?{url.query}"

    websocket_key = base64.b64encode(os.urandom(16)).decode("ascii")

    with socket.create_connection((host, port), timeout=10) as sock:
        sock.settimeout(10)

        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {websocket_key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )

        sock.sendall(request.encode("ascii"))

        # Fontos: a handshake után ugyanabban a TCP-csomagban már
        # WebSocket-adat is érkezhet. Ezt nem szabad eldobni.
        receive_buffer = bytearray()

        while b"\r\n\r\n" not in receive_buffer:
            chunk = sock.recv(4096)

            if not chunk:
                raise SystemExit(
                    "Connection closed during WebSocket handshake"
                )

            receive_buffer.extend(chunk)

            if len(receive_buffer) > 65536:
                raise SystemExit("WebSocket handshake headers are too large")

        header_end = receive_buffer.index(b"\r\n\r\n") + 4
        header_bytes = bytes(receive_buffer[:header_end])

        # Megőrizzük a handshake után már beérkezett WebSocket-bájtokat.
        del receive_buffer[:header_end]

        header_text = header_bytes.decode("iso-8859-1")
        header_lines = header_text.split("\r\n")
        status_line = header_lines[0]

        if " 101 " not in status_line:
            raise SystemExit(
                f"WebSocket handshake failed: {status_line}"
            )

        headers: dict[str, str] = {}

        for line in header_lines[1:]:
            if not line or ":" not in line:
                continue

            name, value = line.split(":", 1)
            headers[name.strip().lower()] = value.strip()

        expected_accept = base64.b64encode(
            hashlib.sha1(
                (
                    websocket_key
                    + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
                ).encode("ascii")
            ).digest()
        ).decode("ascii")

        actual_accept = headers.get("sec-websocket-accept")

        if actual_accept != expected_accept:
            raise SystemExit("WebSocket accept key mismatch")

        def read_exact(length: int) -> bytes:
            if length < 0:
                raise SystemExit("Invalid negative WebSocket length")

            while len(receive_buffer) < length:
                chunk = sock.recv(min(max(length - len(receive_buffer), 1), 65536))

                if not chunk:
                    raise SystemExit(
                        "Connection closed while reading WebSocket frame"
                    )

                receive_buffer.extend(chunk)

            result = bytes(receive_buffer[:length])
            del receive_buffer[:length]
            return result

        def read_websocket_frame() -> tuple[bool, int, bytes]:
            first_byte, second_byte = read_exact(2)

            fin = bool(first_byte & 0x80)
            opcode = first_byte & 0x0F
            masked = bool(second_byte & 0x80)
            payload_length = second_byte & 0x7F

            if payload_length == 126:
                payload_length = struct.unpack(
                    "!H",
                    read_exact(2),
                )[0]
            elif payload_length == 127:
                payload_length = struct.unpack(
                    "!Q",
                    read_exact(8),
                )[0]

            if payload_length > MAX_MESSAGE_SIZE:
                raise SystemExit(
                    f"WebSocket frame is too large: {payload_length} bytes"
                )

            masking_key = read_exact(4) if masked else None
            payload = bytearray(read_exact(payload_length))

            if masking_key is not None:
                for index in range(len(payload)):
                    payload[index] ^= masking_key[index % 4]

            return fin, opcode, bytes(payload)

        message = bytearray()
        message_opcode: int | None = None

        while True:
            fin, opcode, payload = read_websocket_frame()

            if opcode == 0x8:
                raise SystemExit(
                    "WebSocket server closed the connection before a frame arrived"
                )

            # Ping/pong vezérlő frame-eket a smoke teszt átugorhatja.
            if opcode in (0x9, 0xA):
                continue

            if opcode in (0x1, 0x2):
                if message_opcode is not None:
                    raise SystemExit(
                        "Unexpected new WebSocket data message"
                    )

                message_opcode = opcode
                message.extend(payload)

            elif opcode == 0x0:
                if message_opcode is None:
                    raise SystemExit(
                        "Unexpected WebSocket continuation frame"
                    )

                message.extend(payload)

            else:
                raise SystemExit(
                    f"Unsupported WebSocket opcode: {opcode}"
                )

            if len(message) > MAX_MESSAGE_SIZE:
                raise SystemExit("WebSocket message is too large")

            if fin:
                break

        if message_opcode != 0x1:
            raise SystemExit("Expected a text WebSocket message")

        try:
            decoded_message = message.decode("utf-8")
        except UnicodeDecodeError as error:
            raise SystemExit(
                f"WebSocket message is not valid UTF-8: {error}"
            ) from error

        try:
            frame = json.loads(decoded_message)
        except json.JSONDecodeError as error:
            preview = decoded_message[
                max(0, error.pos - 100):error.pos + 100
            ]

            raise SystemExit(
                "Invalid SpectrumFrame JSON: "
                f"{error}; nearby content={preview!r}"
            ) from error

        required_fields = {
            "schema_version",
            "sensor_id",
            "source_type",
            "sequence",
            "timestamp",
            "powers_dbm",
            "num_points",
        }

        missing_fields = required_fields - frame.keys()

        if missing_fields:
            raise SystemExit(
                "Missing SpectrumFrame fields: "
                f"{sorted(missing_fields)}"
            )

        powers = frame["powers_dbm"]
        number_of_points = frame["num_points"]

        if not isinstance(powers, list):
            raise SystemExit("powers_dbm must be an array")

        if number_of_points != len(powers):
            raise SystemExit(
                "num_points does not match powers_dbm length"
            )

        print(
            json.dumps(
                {
                    "status": "ok",
                    "sequence": frame["sequence"],
                    "points": number_of_points,
                    "source_type": frame["source_type"],
                },
                ensure_ascii=False,
            )
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
