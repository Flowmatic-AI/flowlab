from collections.abc import Iterator

import pytest

from flowlab import FlowLab


@pytest.fixture(autouse=True)
def _reset_flowlab() -> Iterator[None]:
    FlowLab.reset()
    yield
    FlowLab.reset()
