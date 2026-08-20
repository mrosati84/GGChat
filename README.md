# ggchat

`ggchat` is a small, ephemeral desktop chat that broadcasts text through
ultrasound. Dear PyGui provides the interface, ggwave encodes and decodes the
data, and sounddevice connects it to the default microphone and speaker.

Messages are filtered locally by a case-sensitive room name. Rooms are not
private: there is no encryption, authentication, delivery acknowledgement, or
collision avoidance.

## Requirements

- Python 3.11 or newer
- A microphone and speaker capable of handling ggwave's ultrasonic frequencies
- OS permission to use the microphone

## Run

```bash
uv sync
uv run python -m ggchat
```

The installed `ggchat` command is equivalent.

On startup, choose a nickname and room. Each must be 1–10 ASCII letters or
digits, with optional single hyphens between parts, such as `matteo`, `games`,
or `ita-dev`.

Messages are single-line and limited to 98 UTF-8 bytes. The UI displays the
current byte count because accented characters occupy more than one byte.

## Test

```bash
uv run pytest
```

## Protocol

The application payload is a versioned binary packet capped at ggwave's
140-byte variable-payload maximum:

```text
magic(2) | version(1) | UUIDv4(16) |
room length(1) | nickname length(1) | message length(1) |
room(1–10) | nickname(1–10) | message(1–98)
```

UUIDs suppress loopback and duplicate messages. Packets with another room,
unknown framing, invalid fields, or an unsupported protocol version are ignored.
All chat history and configuration exist only in memory and disappear when the
application exits.
