from pymmcore_remote import remote_mmcore


def test_client():
    with remote_mmcore() as (mmcore, signals):
        assert mmcore._pyroUri
