import struct
import uuid

import pytest

from ggchat.protocol import (
    ChatPacket,
    MAX_PACKET_BYTES,
    PacketError,
    decode_packet,
    encode_packet,
    normalize_message,
    normalize_name,
    truncate_utf8,
)


def test_maximum_packet_is_exactly_140_bytes() -> None:
    packet = ChatPacket(uuid.uuid4(), "a" * 10, "b" * 10, "c" * 98)
    encoded = encode_packet(packet)
    assert len(encoded) == MAX_PACKET_BYTES
    assert decode_packet(encoded) == packet


def test_round_trip_preserves_utf8_message() -> None:
    packet = ChatPacket(uuid.uuid4(), "ita-dev", "matteo", "Perché è già così?")
    assert decode_packet(encode_packet(packet)) == packet


@pytest.mark.parametrize(
    "name",
    ["", " ", "dev room", "-dev", "dev-", "dev--room", "caffè", "dev_room", "a" * 11],
)
def test_invalid_names_are_rejected(name: str) -> None:
    with pytest.raises(PacketError):
        normalize_name(name)


def test_names_are_trimmed_and_case_sensitive() -> None:
    assert normalize_name("  Ita-Dev  ") == "Ita-Dev"
    assert normalize_name("Ita") != normalize_name("ita")


def test_messages_are_trimmed_and_limited_by_utf8_bytes() -> None:
    assert normalize_message("  caffè  ") == "caffè"
    assert len(truncate_utf8("è" * 60).encode("utf-8")) == 98
    with pytest.raises(PacketError):
        normalize_message("è" * 50)


def test_empty_and_multiline_messages_are_rejected() -> None:
    with pytest.raises(PacketError):
        normalize_message("   ")
    with pytest.raises(PacketError):
        normalize_message("one\ntwo")


def test_decoder_rejects_wrong_magic_and_length() -> None:
    encoded = bytearray(encode_packet(ChatPacket(uuid.uuid4(), "room", "nick", "hello")))
    encoded[0:2] = b"XX"
    with pytest.raises(PacketError):
        decode_packet(bytes(encoded))

    valid = encode_packet(ChatPacket(uuid.uuid4(), "room", "nick", "hello"))
    with pytest.raises(PacketError):
        decode_packet(valid[:-1])


def test_decoder_rejects_unsupported_version() -> None:
    encoded = bytearray(encode_packet(ChatPacket(uuid.uuid4(), "room", "nick", "hello")))
    encoded[2] = 99
    with pytest.raises(PacketError):
        decode_packet(bytes(encoded))


def test_decoder_rejects_invalid_utf8() -> None:
    packet = bytearray(encode_packet(ChatPacket(uuid.uuid4(), "room", "nick", "hello")))
    header_size = struct.calcsize("!2sB16sBBB")
    message_offset = header_size + len("room") + len("nick")
    packet[message_offset] = 0xFF
    with pytest.raises(PacketError):
        decode_packet(bytes(packet))
