from typing import ClassVar

from flowlab.modules.auth import BaseUser


class User(BaseUser):
    __fillable__: ClassVar[tuple[str, ...]] = ()
