from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

try:
    from IPython import get_ipython  # pyright: ignore
    from IPython.core.completer import CompletionContext
    from IPython.core.interactiveshell import InteractiveShell
except ImportError:
    # If IPython is not installed, we cannot run these tests.
    pytest.skip("IPython is not installed", allow_module_level=True)

from pymmcore_plus._ipy_completion import (
    cmmcoreplus_matcher,
    install_pymmcore_ipy_completion,
)
from pymmcore_plus.core._constants import DeviceType
from pymmcore_plus.core._mmcore_plus import CMMCorePlus

if TYPE_CHECKING:
    from IPython.core.completer import SimpleMatcherResult

CORE_NAME = "core"  # name of the CMMCorePlus instance in the shell's namespace
OTHER_NAME = "not_core"  # name of a non-CMMCorePlus instance in the shell's namespace


class _StubShell:
    def __init__(self, ns: dict | None = None) -> None:
        self.user_ns: dict = ns or {}


@pytest.fixture
def mock_shell(monkeypatch: pytest.MonkeyPatch) -> _StubShell:
    """Provide a dummy `get_ipython()` that only exposes `.user_ns`."""
    shell = _StubShell()

    monkeypatch.setattr(InteractiveShell, "initialized", lambda: True, raising=False)
    monkeypatch.setattr(InteractiveShell, "instance", lambda: shell, raising=False)

    assert get_ipython() is shell  # type: ignore[no-untyped-call]
    return shell


@pytest.fixture
def shell_core(mock_shell: _StubShell) -> CMMCorePlus:
    """Populate the stub's namespace with a CMMCorePlus instance."""
    mock_shell.user_ns[CORE_NAME] = c = CMMCorePlus()
    mock_shell.user_ns[OTHER_NAME] = object()  # a non-CMMCorePlus object
    c.loadSystemConfiguration()
    return c


# helpers ------------------------------------------------------------------


def _unwrap_completions(result: SimpleMatcherResult) -> set[str]:
    """Unwraps the completions from the matcher."""
    # eval here because the completions return reprs (e.g., 'setCameraDevice')
    return {eval(c.text) for c in result["completions"]}


def _make_context(text: str) -> CompletionContext:
    """Create a CompletionContext for testing."""
    return CompletionContext(
        token="", full_text=text, cursor_position=len(text), cursor_line=0, limit=500
    )


def _get_completions(text: str) -> set[str]:
    """Get completions for a given text using the cmmcoreplus_matcher."""
    ctx = _make_context(text)
    return _unwrap_completions(cmmcoreplus_matcher(ctx))


# ------------------------------------------------------------------


def test_null_completion(shell_core: CMMCorePlus) -> None:
    # some other object, that happens to have a method named 'setCameraDevice'
    assert _get_completions(f"{OTHER_NAME}.setCameraDevice(") == set()
    # some other object, not in the namespace
    assert _get_completions("not_in_namespace.setCameraDevice(") == set()
    # no paren after the method name
    assert _get_completions(f"{CORE_NAME}.setCameraDevice") == set()
    # valid core method... but no completions available
    assert _get_completions(f"{CORE_NAME}.getLoadedDevices(") == set()


EXPECTED_DEVICE_COMPLETIONS: list[tuple[str, DeviceType]] = [
    (CMMCorePlus.setCameraDevice.__name__, DeviceType.Camera),
    (CMMCorePlus.setFocusDevice.__name__, DeviceType.Stage),
    (CMMCorePlus.setXYStageDevice.__name__, DeviceType.XYStage),
    (CMMCorePlus.setAutoFocusDevice.__name__, DeviceType.AutoFocus),
    (CMMCorePlus.setGalvoDevice.__name__, DeviceType.Galvo),
    (CMMCorePlus.setImageProcessorDevice.__name__, DeviceType.ImageProcessor),
    (CMMCorePlus.setShutterDevice.__name__, DeviceType.Shutter),
    (CMMCorePlus.setSLMDevice.__name__, DeviceType.SLM),
    (CMMCorePlus.hasProperty.__name__, DeviceType.Any),
]


@pytest.mark.parametrize("method_name, device_type", EXPECTED_DEVICE_COMPLETIONS)
def test_device_completions(
    shell_core: CMMCorePlus, method_name: str, device_type: DeviceType
) -> None:
    completions = _get_completions(f"{CORE_NAME}.{method_name}(")

    if device_type == DeviceType.Any:
        # Unlike getLoadedDevicesOfType(Any) ... getLoadedDevices include 'Core'
        expect: set[str] = set(shell_core.getLoadedDevices())
    else:
        expect = set(shell_core.getLoadedDevicesOfType(device_type))

    if method_name.startswith("set"):
        # add the empty string, because you can set the device to nothing
        expect.add("")

    assert completions == expect


@pytest.mark.parametrize(
    "method_name, dev_label",
    [
        ("getProperty", "Camera"),
        ("getProperty", "XY"),
        ("getProperty", "Objective"),
        ("getAllowedPropertyValues", "Camera"),
        ("getPropertyFromCache", "Camera"),
        ("getPropertyLowerLimit", "Camera"),
        ("getPropertySequenceMaxLength", "Camera"),
        ("getPropertyType", "Z"),
        ("hasProperty", "XY"),
    ],
)
def test_property_completions(
    shell_core: CMMCorePlus, method_name: str, dev_label: str
) -> None:
    completions = _get_completions(f"{CORE_NAME}.{method_name}('{dev_label}', ")
    expect = set(shell_core.getDevicePropertyNames(dev_label))
    assert completions == expect


def test_config_completions(shell_core: CMMCorePlus) -> None:
    completions = _get_completions(f"{CORE_NAME}.getAvailableConfigs(")
    expect = set(shell_core.getAvailableConfigGroups())
    assert completions == expect

    group_name = expect.pop()
    completions = _get_completions(f"{CORE_NAME}.getConfigData('{group_name}', ")
    expect = set(shell_core.getAvailableConfigs(group_name))
    assert completions == expect


def test_install_script() -> None:
    # CREATE a new ipython shell instance
    shell = InteractiveShell.instance()
    try:
        assert shell
        install_pymmcore_ipy_completion()
        assert cmmcoreplus_matcher in shell.Completer.custom_matchers
    finally:
        InteractiveShell.clear_instance()
