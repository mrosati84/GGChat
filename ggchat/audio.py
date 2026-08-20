"""Full-duplex sounddevice transport for ggwave packets."""

from __future__ import annotations

from dataclasses import dataclass
from queue import SimpleQueue
from threading import Lock
from typing import Literal

import ggwave
import numpy as np
import sounddevice as sd

# ggwave's native diagnostics include decoded payloads. The GUI reports useful
# errors itself, so keep ephemeral chat content out of terminal logs.
ggwave.disableLog()

SAMPLE_RATE = 48_000
BLOCK_SIZE = 1_024
CHANNELS = 1
ULTRASOUND_NORMAL_PROTOCOL = 3
ENCODER_VOLUME = 10


@dataclass(frozen=True, slots=True)
class AudioEvent:
    kind: Literal["received", "progress", "sent", "error"]
    value: bytes | float | str | None = None


class AudioTransport:
    """Own the input stream, decoder, and at most one output stream."""

    def __init__(self, events: SimpleQueue[AudioEvent]) -> None:
        self.events = events
        self._decoder: int | None = None
        self._input: sd.InputStream | None = None
        self._output: sd.OutputStream | None = None
        self._tx_samples: np.ndarray | None = None
        self._tx_position = 0
        self._tx_failed = False
        self._lock = Lock()

    @property
    def transmitting(self) -> bool:
        with self._lock:
            return self._output is not None

    def start(self) -> None:
        """Open and start default input; also validate default output."""
        self.close()
        sd.check_input_settings(
            device=None, channels=CHANNELS, dtype="float32", samplerate=SAMPLE_RATE
        )
        sd.check_output_settings(
            device=None, channels=CHANNELS, dtype="float32", samplerate=SAMPLE_RATE
        )
        self._decoder = ggwave.init()
        self._input = sd.InputStream(
            samplerate=SAMPLE_RATE,
            blocksize=BLOCK_SIZE,
            channels=CHANNELS,
            dtype="float32",
            callback=self._on_input,
        )
        try:
            self._input.start()
        except Exception:
            self.close()
            raise

    def send(self, payload: bytes) -> None:
        """Encode and asynchronously play one packet."""
        with self._lock:
            if self._output is not None:
                raise RuntimeError("A transmission is already in progress")

        waveform = ggwave.encode(
            payload,
            protocolId=ULTRASOUND_NORMAL_PROTOCOL,
            volume=ENCODER_VOLUME,
        )
        if not waveform:
            raise RuntimeError("ggwave could not encode the message")
        samples = np.frombuffer(waveform, dtype=np.float32).copy()
        if not samples.size:
            raise RuntimeError("ggwave produced an empty waveform")

        stream = sd.OutputStream(
            samplerate=SAMPLE_RATE,
            blocksize=BLOCK_SIZE,
            channels=CHANNELS,
            dtype="float32",
            callback=self._on_output,
            finished_callback=self._on_output_finished,
        )
        with self._lock:
            self._tx_samples = samples
            self._tx_position = 0
            self._tx_failed = False
            self._output = stream
        try:
            stream.start()
        except Exception:
            with self._lock:
                self._output = None
                self._tx_samples = None
            stream.close()
            raise

    def close(self) -> None:
        """Release audio streams and the native decoder instance."""
        with self._lock:
            output, self._output = self._output, None
            self._tx_samples = None
        if output is not None:
            try:
                output.abort(ignore_errors=True)
                output.close(ignore_errors=True)
            except Exception:
                pass
        input_stream, self._input = self._input, None
        if input_stream is not None:
            try:
                input_stream.stop(ignore_errors=True)
                input_stream.close(ignore_errors=True)
            except Exception:
                pass
        decoder, self._decoder = self._decoder, None
        if decoder is not None:
            ggwave.free(decoder)

    def _on_input(self, indata, frames, time_info, status) -> None:  # noqa: ANN001
        if status:
            self.events.put(AudioEvent("error", f"Microphone: {status}"))
        decoder = self._decoder
        if decoder is None:
            return
        try:
            decoded = ggwave.decode(decoder, indata.tobytes())
            if decoded is not None:
                self.events.put(AudioEvent("received", bytes(decoded)))
        except Exception as exc:
            self.events.put(AudioEvent("error", f"Decoder: {exc}"))

    def _on_output(self, outdata, frames, time_info, status) -> None:  # noqa: ANN001
        if status:
            self._tx_failed = True
            self.events.put(AudioEvent("error", f"Speaker: {status}"))
        samples = self._tx_samples
        if samples is None:
            outdata.fill(0)
            raise sd.CallbackAbort

        remaining = samples.size - self._tx_position
        count = min(frames, remaining)
        outdata[:count, 0] = samples[self._tx_position : self._tx_position + count]
        if count < frames:
            outdata[count:, 0] = 0
        self._tx_position += count
        self.events.put(AudioEvent("progress", self._tx_position / samples.size))
        if self._tx_position >= samples.size:
            raise sd.CallbackStop

    def _on_output_finished(self) -> None:
        with self._lock:
            stream, self._output = self._output, None
            completed = (
                self._tx_samples is not None
                and self._tx_position >= self._tx_samples.size
                and not self._tx_failed
            )
            self._tx_samples = None
        if stream is not None:
            try:
                stream.close(ignore_errors=True)
            except Exception:
                pass
        self.events.put(AudioEvent("sent" if completed else "error", None if completed else "Transmission failed"))
