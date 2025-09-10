from collections.abc import Iterator
from unittest.mock import patch

import pytest

from pymmcore_plus.experimental.unicore.core import _unicore


@pytest.fixture(autouse=True)
def smaller_default_buffer() -> Iterator[None]:
    """Set the default buffer size to 250 for tests."""
    with patch.object(_unicore, "_DEFAULT_BUFFER_SIZE_MB", 250):
        yield
