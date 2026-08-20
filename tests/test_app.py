import pytest

from ggchat.app import mentions_user


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
