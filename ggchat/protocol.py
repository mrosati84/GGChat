"""Compact binary wire protocol used inside a ggwave payload."""

from __future__ import annotations

from dataclasses import dataclass
import re
import struct
import uuid

MAGIC = b"GC"
VERSION = 1
MAX_PACKET_BYTES = 140
MAX_NAME_BYTES = 10
MAX_MESSAGE_BYTES = 98

_HEADER = struct.Struct("!2sB16sBBB")
_NAME_RE = re.compile(r"^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*$")


class PacketError(ValueError):
    """Raised when an application packet is invalid."""


@dataclass(frozen=True, slots=True)
class ChatPacket:
    message_id: uuid.UUID
    room: str
    nickname: str
    message: str


def normalize_name(value: str, field: str = "Name") -> str:
    """Trim and validate a nickname or room name."""
    normalized = value.strip()
    if not normalized:
        raise PacketError(f"{field} is required")
    try:
        encoded = normalized.encode("ascii")
    except UnicodeEncodeError as exc:
        raise PacketError(f"{field} must use ASCII letters, digits, and hyphens") from exc
    if len(encoded) > MAX_NAME_BYTES:
        raise PacketError(f"{field} must be at most {MAX_NAME_BYTES} characters")
    if _NAME_RE.fullmatch(normalized) is None:
        raise PacketError(
            f"{field} must contain letters or digits separated only by single hyphens"
        )
    return normalized


def normalize_message(value: str) -> str:
    """Trim and validate a message body."""
    normalized = value.strip()
    if not normalized:
        raise PacketError("Message cannot be empty")
    if "\n" in normalized or "\r" in normalized:
        raise PacketError("Message must be a single line")
    if len(normalized.encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise PacketError(f"Message must be at most {MAX_MESSAGE_BYTES} UTF-8 bytes")
    return normalized


def truncate_utf8(value: str, limit: int = MAX_MESSAGE_BYTES) -> str:
    """Return the longest prefix whose UTF-8 representation fits in *limit*."""
    encoded = value.encode("utf-8")
    if len(encoded) <= limit:
        return value
    return encoded[:limit].decode("utf-8", errors="ignore")


def encode_packet(packet: ChatPacket) -> bytes:
    room = normalize_name(packet.room, "Room").encode("ascii")
    nickname = normalize_name(packet.nickname, "Nickname").encode("ascii")
    message = normalize_message(packet.message).encode("utf-8")
    header = _HEADER.pack(
        MAGIC,
        VERSION,
        packet.message_id.bytes,
        len(room),
        len(nickname),
        len(message),
    )
    payload = header + room + nickname + message
    if len(payload) > MAX_PACKET_BYTES:
        raise PacketError("Packet exceeds ggwave's variable-payload limit")
    return payload


def decode_packet(payload: bytes) -> ChatPacket:
    if len(payload) < _HEADER.size:
        raise PacketError("Packet is too short")
    if len(payload) > MAX_PACKET_BYTES:
        raise PacketError("Packet is too long")

    magic, version, raw_id, room_len, nickname_len, message_len = _HEADER.unpack_from(
        payload
    )
    if magic != MAGIC:
        raise PacketError("Unknown packet magic")
    if version != VERSION:
        raise PacketError("Unsupported packet version")
    if not 1 <= room_len <= MAX_NAME_BYTES:
        raise PacketError("Invalid room length")
    if not 1 <= nickname_len <= MAX_NAME_BYTES:
        raise PacketError("Invalid nickname length")
    if not 1 <= message_len <= MAX_MESSAGE_BYTES:
        raise PacketError("Invalid message length")

    expected = _HEADER.size + room_len + nickname_len + message_len
    if len(payload) != expected:
        raise PacketError("Packet length does not match its header")

    offset = _HEADER.size
    room_raw = payload[offset : offset + room_len]
    offset += room_len
    nickname_raw = payload[offset : offset + nickname_len]
    offset += nickname_len
    message_raw = payload[offset : offset + message_len]

    try:
        room = room_raw.decode("ascii")
        nickname = nickname_raw.decode("ascii")
        message = message_raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PacketError("Packet contains invalid text encoding") from exc

    room = normalize_name(room, "Room")
    nickname = normalize_name(nickname, "Nickname")
    message = normalize_message(message)
    if len(message.encode("utf-8")) != message_len:
        raise PacketError("Message encoding is not canonical")

    return ChatPacket(uuid.UUID(bytes=raw_id), room, nickname, message)
