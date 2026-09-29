import random

from flowlab import CommandRouter

router = CommandRouter()

QUOTES = [
    "Simplicity is the ultimate sophistication.",
    "Make it work, make it right, make it fast.",
    "Well begun is half done.",
]


@router.command("inspire:quote")
def quote() -> None:
    print(random.choice(QUOTES))
