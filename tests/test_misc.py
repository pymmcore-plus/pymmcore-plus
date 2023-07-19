from unittest.mock import Mock

import pytest
from pymmcore_plus._util import retry


def test_retry() -> None:
    i: int = 0

    def works_on_third_try(x: str) -> str:
        nonlocal i
        i += 1
        if i < 3:
            raise ValueError("nope")
        return x

    with pytest.raises(ValueError, match="nope"):
        retry(tries=3, exceptions=RuntimeError, delay=0.5)(works_on_third_try)(1)

    i = 0
    mock = Mock()
    good_retry = retry(tries=3, exceptions=ValueError, logger=mock)(works_on_third_try)

    assert good_retry("hi") == "hi"
    assert mock.call_count == 2
    mock.assert_called_with("ValueError nope caught, trying 1 more times")
