import pytest

from ggchat import app
from ggchat.app import ChatApp, mentions_user


@pytest.mark.parametrize(
    "message",
    [
        "@matteo",
        "hello @matteo",
        "hello @matteo!",
        "(@matteo), are you there?",
    ],
)
def test_exact_mention_matches(message: str) -> None:
    assert mentions_user(message, "matteo")


@pytest.mark.parametrize(
    "message",
    [
        "matteo",
        "@Matteo",
        "@matteo2",
        "@matteo-dev",
        "email@matteo",
    ],
)
def test_non_mentions_do_not_match(message: str) -> None:
    assert not mentions_user(message, "matteo")


def test_hyphenated_nickname_can_be_mentioned() -> None:
    assert mentions_user("hello @ita-dev!", "ita-dev")


def test_ctrl_c_closes_audio_and_destroys_context(monkeypatch) -> None:
    chat = ChatApp()
    calls: list[str] = []

    monkeypatch.setattr(chat, "_create_themes", lambda: None)
    monkeypatch.setattr(chat, "_build_startup", lambda: None)
    monkeypatch.setattr(chat.audio, "close", lambda: calls.append("audio.close"))
    monkeypatch.setattr(app.dpg, "create_context", lambda: calls.append("create_context"))
    monkeypatch.setattr(app.dpg, "create_viewport", lambda **kwargs: None)
    monkeypatch.setattr(app.dpg, "setup_dearpygui", lambda: None)
    monkeypatch.setattr(app.dpg, "show_viewport", lambda: None)
    monkeypatch.setattr(app.dpg, "is_dearpygui_running", lambda: True)
    monkeypatch.setattr(
        app.dpg,
        "render_dearpygui_frame",
        lambda: (_ for _ in ()).throw(KeyboardInterrupt),
    )
    monkeypatch.setattr(app.dpg, "destroy_context", lambda: calls.append("destroy_context"))

    chat.run()

    assert calls == ["create_context", "audio.close", "destroy_context"]
