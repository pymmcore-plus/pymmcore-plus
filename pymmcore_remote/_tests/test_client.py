from pymmcore_remote._client import RemoteMMCore
from pymmcore_remote._server import DEFAULT_URI


def test_client():
    with RemoteMMCore() as mmcore:
        assert str(mmcore._pyroUri) == DEFAULT_URI
