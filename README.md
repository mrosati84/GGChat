# ggchat

`ggchat` is a tiny desktop chat that sends text through sound instead of a
network. Nearby computers exchange short messages over ggwave's ultrasonic
audio protocol; no server, account, or internet connection is involved.

## Requirements

- Python 3.11 or newer and [uv](https://docs.astral.sh/uv/)
- A microphone and speaker that support mono audio at 48 kHz
- Permission for the application or terminal to access the microphone

Ultrasound performance depends heavily on the audio hardware. Laptop speakers
and microphones work best at short range in a quiet room.

## Run and use

```bash
uv sync
uv run python -m ggchat
```

To create a standalone executable with Nuitka, run `make`; the result is
written to `dist/ggchat`. Run `make clean` to remove build artifacts.

On every computer:

1. Choose a nickname and the same case-sensitive room name.
2. Press **Join** and allow microphone access.
3. Type a message and press **Enter** or **Send**.

Names are 1–10 ASCII letters or digits, with optional single hyphens. Messages
are single-line and limited to 98 UTF-8 bytes. An exact `@nickname` mention is
highlighted.

## How it works

[ggwave](https://github.com/ggerganov/ggwave) acts as a small data-over-sound
modem. For each message, `ggchat` builds a binary packet containing a protocol
version, UUID, room, nickname, and UTF-8 text. ggwave encodes that packet with
its **Ultrasound Normal** protocol into a waveform, which `sounddevice` plays as
48 kHz mono audio.

At the same time, the microphone continuously feeds audio blocks to a ggwave
decoder. Valid packets for the selected room are shown in the Dear PyGui
interface. UUIDs suppress loopback and duplicate messages; room filtering
happens locally and provides organization, not privacy.

## Current limitations

- No encryption, authentication, persistent history, or user discovery
- No delivery acknowledgement, retry, or collision handling
- Limited range and reliability; noise, walls, and weak ultrasonic hardware
  can prevent delivery
- Simultaneous transmissions may interfere, and only one local message can be
  sent at a time
- Uses only the system's default audio devices and supports messages up to 98
  UTF-8 bytes

## Possible directions

The project could add device and protocol selection, acknowledgements and
retries, encrypted rooms and identities, multi-packet messages or small file
transfers, and optional network relays that bridge separate acoustic spaces.

## Tests

```bash
uv run pytest
```
