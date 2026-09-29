from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel


class Model(BaseModel):
    __table__: ClassVar[str] = ""
