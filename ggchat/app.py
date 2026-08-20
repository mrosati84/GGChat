"""Dear PyGui application for ggchat."""

from __future__ import annotations

from collections import deque
from datetime import datetime
from queue import Empty, SimpleQueue
import uuid

import dearpygui.dearpygui as dpg

from .audio import AudioEvent, AudioTransport
from .protocol import (
    ChatPacket,
    MAX_MESSAGE_BYTES,
    PacketError,
    decode_packet,
    encode_packet,
    normalize_message,
    normalize_name,
    truncate_utf8,
)


class ChatApp:
    def __init__(self) -> None:
        self.nickname = ""
        self.room = ""
        self.events: SimpleQueue[AudioEvent] = SimpleQueue()
        self.audio = AudioTransport(self.events)
        self.message_items: deque[int | str] = deque()
        self.seen_ids: set[uuid.UUID] = set()
        self.seen_order: deque[uuid.UUID] = deque()
        self.joined = False
        self._editing_composer = False

    def run(self) -> None:
        dpg.create_context()
        try:
            self._create_themes()
            self._build_startup()
            dpg.create_viewport(
                title="ggchat", width=760, height=600, min_width=520, min_height=420
            )
            dpg.setup_dearpygui()
            dpg.show_viewport()
            while dpg.is_dearpygui_running():
                self._drain_audio_events()
                dpg.render_dearpygui_frame()
        finally:
            self.audio.close()
            dpg.destroy_context()

    def _create_themes(self) -> None:
        with dpg.theme(tag="outgoing_theme"):
            with dpg.theme_component(dpg.mvText):
                dpg.add_theme_color(dpg.mvThemeCol_Text, (105, 190, 255))
        with dpg.theme(tag="incoming_theme"):
            with dpg.theme_component(dpg.mvText):
                dpg.add_theme_color(dpg.mvThemeCol_Text, (225, 225, 225))
        with dpg.theme(tag="error_theme"):
            with dpg.theme_component(dpg.mvText):
                dpg.add_theme_color(dpg.mvThemeCol_Text, (255, 105, 105))

    def _build_startup(self) -> None:
        with dpg.window(tag="startup_window", label="Join ggchat", no_close=True):
            dpg.add_spacer(height=20)
            dpg.add_text("Chat over ultrasound", color=(105, 190, 255))
            dpg.add_text("Choose a nickname and room for this session.")
            dpg.add_spacer(height=12)
            dpg.add_input_text(
                tag="nickname_input",
                label="Nickname",
                hint="e.g. matteo",
                width=300,
                on_enter=True,
                callback=self._join,
            )
            dpg.add_input_text(
                tag="room_input",
                label="Room",
                hint="e.g. ita-dev",
                width=300,
                on_enter=True,
                callback=self._join,
            )
            dpg.add_text("1-10 ASCII letters/digits; single hyphens may separate parts.")
            dpg.add_spacer(height=8)
            dpg.add_button(tag="join_button", label="Join", callback=self._join, width=100)
            dpg.add_loading_indicator(tag="join_loading", show=False, radius=2.5)
            dpg.add_text("", tag="startup_error", show=False)
            dpg.bind_item_theme("startup_error", "error_theme")
        dpg.set_primary_window("startup_window", True)

    def _join(self, sender=None, app_data=None, user_data=None) -> None:  # noqa: ANN001
        if self.joined:
            return
        try:
            nickname = normalize_name(dpg.get_value("nickname_input"), "Nickname")
            room = normalize_name(dpg.get_value("room_input"), "Room")
        except PacketError as exc:
            self._show_startup_error(str(exc))
            return

        dpg.configure_item("join_button", enabled=False)
        dpg.configure_item("join_loading", show=True)
        dpg.configure_item("startup_error", show=False)
        try:
            self.audio.start()
        except Exception as exc:
            dpg.configure_item("join_button", enabled=True)
            dpg.configure_item("join_loading", show=False)
            self._show_startup_error(f"Could not open the default audio devices: {exc}")
            return

        self.nickname = nickname
        self.room = room
        self.joined = True
        self._build_chat()
        dpg.delete_item("startup_window")
        dpg.set_primary_window("chat_window", True)
        dpg.focus_item("composer")

    def _show_startup_error(self, message: str) -> None:
        dpg.set_value("startup_error", message)
        dpg.configure_item("startup_error", show=True)

    def _build_chat(self) -> None:
        with dpg.window(tag="chat_window", label="ggchat", no_close=True):
            with dpg.group(horizontal=True):
                dpg.add_text(f"{self.nickname}  |  #{self.room}", color=(105, 190, 255))
                dpg.add_spacer(width=12)
                dpg.add_text("Listening", tag="audio_status", color=(125, 220, 145))
                dpg.add_button(
                    tag="retry_audio",
                    label="Retry audio",
                    callback=self._retry_audio,
                    show=False,
                )
            dpg.add_separator()
            with dpg.child_window(tag="history", autosize_x=True, height=-105, border=False):
                dpg.add_text("No messages yet.", tag="empty_history", color=(140, 140, 140))
            dpg.add_progress_bar(
                tag="send_progress",
                default_value=0.0,
                overlay="Transmitting 0%",
                width=-1,
                show=False,
            )
            with dpg.group(horizontal=True):
                dpg.add_input_text(
                    tag="composer",
                    hint="Message",
                    width=-110,
                    on_enter=True,
                    callback=self._send,
                )
                dpg.add_button(tag="send_button", label="Send", width=90, callback=self._send)
            with dpg.group(horizontal=True):
                dpg.add_text(f"0 / {MAX_MESSAGE_BYTES} bytes", tag="byte_counter")
                dpg.add_spacer(width=15)
                dpg.add_text("Listening", tag="send_status")
        # Dear PyGui has one callback per item. Route edits and Enter separately
        # through an item handler instead of replacing the send callback.
        with dpg.item_handler_registry(tag="composer_handlers"):
            dpg.add_item_edited_handler(callback=self._composer_changed)
        dpg.bind_item_handler_registry("composer", "composer_handlers")

    def _composer_changed(self, sender, app_data, user_data=None) -> None:  # noqa: ANN001
        if self._editing_composer:
            return
        value = dpg.get_value("composer").replace("\r", " ").replace("\n", " ")
        limited = truncate_utf8(value)
        if limited != dpg.get_value("composer"):
            self._editing_composer = True
            dpg.set_value("composer", limited)
            self._editing_composer = False
        used = len(limited.encode("utf-8"))
        dpg.set_value("byte_counter", f"{used} / {MAX_MESSAGE_BYTES} bytes")

    def _send(self, sender=None, app_data=None, user_data=None) -> None:  # noqa: ANN001
        if not self.joined or self.audio.transmitting:
            return
        try:
            message = normalize_message(dpg.get_value("composer"))
            packet = ChatPacket(uuid.uuid4(), self.room, self.nickname, message)
            payload = encode_packet(packet)
        except PacketError as exc:
            dpg.set_value("send_status", str(exc))
            return

        self._remember(packet.message_id)
        self._append_message(packet.nickname, packet.message, outgoing=True)
        dpg.set_value("composer", "")
        dpg.set_value("byte_counter", f"0 / {MAX_MESSAGE_BYTES} bytes")
        self._set_transmitting(True)
        try:
            self.audio.send(payload)
        except Exception as exc:
            self._set_transmitting(False)
            self._show_audio_error(f"Transmission failed: {exc}")

    def _set_transmitting(self, active: bool) -> None:
        dpg.configure_item("composer", enabled=not active)
        dpg.configure_item("send_button", enabled=not active)
        dpg.configure_item("send_progress", show=active)
        if active:
            dpg.set_value("send_progress", 0.0)
            dpg.configure_item("send_progress", overlay="Transmitting 0%")
            dpg.set_value("send_status", "Transmitting")
        else:
            dpg.focus_item("composer")

    def _append_message(self, nickname: str, message: str, *, outgoing: bool) -> None:
        if dpg.does_item_exist("empty_history"):
            dpg.delete_item("empty_history")
        timestamp = datetime.now().strftime("%H:%M:%S")
        item = dpg.add_text(
            f"[{timestamp}] {nickname}: {message}", parent="history", wrap=700
        )
        dpg.bind_item_theme(item, "outgoing_theme" if outgoing else "incoming_theme")
        self.message_items.append(item)
        if len(self.message_items) > 500:
            dpg.delete_item(self.message_items.popleft())
        dpg.set_y_scroll("history", dpg.get_y_scroll_max("history"))

    def _remember(self, message_id: uuid.UUID) -> None:
        if message_id in self.seen_ids:
            return
        self.seen_ids.add(message_id)
        self.seen_order.append(message_id)
        if len(self.seen_order) > 2_048:
            self.seen_ids.discard(self.seen_order.popleft())

    def _drain_audio_events(self) -> None:
        while True:
            try:
                event = self.events.get_nowait()
            except Empty:
                break
            if not self.joined:
                continue
            if event.kind == "received" and isinstance(event.value, bytes):
                self._handle_received(event.value)
            elif event.kind == "progress" and isinstance(event.value, float):
                progress = min(max(event.value, 0.0), 1.0)
                dpg.set_value("send_progress", progress)
                dpg.configure_item("send_progress", overlay=f"Transmitting {progress:.0%}")
            elif event.kind == "sent":
                self._set_transmitting(False)
                dpg.configure_item("send_progress", show=False)
                dpg.set_value("send_status", "Sent")
                dpg.set_value("audio_status", "Listening")
            elif event.kind == "error":
                self._set_transmitting(False)
                self._show_audio_error(str(event.value or "Unknown audio error"))

    def _handle_received(self, payload: bytes) -> None:
        try:
            packet = decode_packet(payload)
        except PacketError:
            return
        if packet.room != self.room or packet.message_id in self.seen_ids:
            return
        self._remember(packet.message_id)
        self._append_message(packet.nickname, packet.message, outgoing=False)

    def _show_audio_error(self, message: str) -> None:
        dpg.configure_item("send_progress", show=False)
        dpg.set_value("audio_status", "Audio error")
        dpg.set_value("send_status", message)
        dpg.configure_item("retry_audio", show=True)
        dpg.configure_item("send_button", enabled=False)

    def _retry_audio(self, sender=None, app_data=None, user_data=None) -> None:  # noqa: ANN001
        dpg.configure_item("retry_audio", enabled=False)
        dpg.set_value("send_status", "Reopening default audio devices...")
        try:
            self.audio.start()
        except Exception as exc:
            dpg.set_value("send_status", f"Audio retry failed: {exc}")
            dpg.configure_item("retry_audio", enabled=True)
            return
        dpg.set_value("audio_status", "Listening")
        dpg.set_value("send_status", "Listening")
        dpg.configure_item("retry_audio", show=False, enabled=True)
        dpg.configure_item("composer", enabled=True)
        dpg.configure_item("send_button", enabled=True)
        dpg.focus_item("composer")


def main() -> None:
    ChatApp().run()


if __name__ == "__main__":
    main()
