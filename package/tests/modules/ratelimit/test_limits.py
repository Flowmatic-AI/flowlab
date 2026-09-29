import pytest

from flowlab.modules.ratelimit import Limit


@pytest.mark.parametrize(
    ("text", "attempts", "seconds"),
    [
        ("5/minute", 5, 60),
        ("100/hours", 100, 3600),
        (" 10 / 5 minutes ", 10, 300),
        ("1/second", 1, 1),
        ("1000/Day", 1000, 86400),
    ],
)
def test_parse(text: str, attempts: int, seconds: int) -> None:
    assert Limit.parse(text) == Limit(attempts, seconds)


@pytest.mark.parametrize("text", ["", "5", "5/fortnight", "five/minute", "0/minute", "5/0 minutes", "-1/minute"])
def test_parse_rejects_nonsense(text: str) -> None:
    with pytest.raises(ValueError):
        Limit.parse(text)


@pytest.mark.parametrize(
    ("text", "canonical"),
    [
        ("5/minutes", "5/minute"),
        ("10/5 minutes", "10/5 minutes"),
        ("3/60 seconds", "3/minute"),
        ("7/90 seconds", "7/90 seconds"),
    ],
)
def test_str_is_the_canonical_form(text: str, canonical: str) -> None:
    assert str(Limit.parse(text)) == canonical
