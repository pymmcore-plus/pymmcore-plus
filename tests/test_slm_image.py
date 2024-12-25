from unittest.mock import MagicMock

import numpy as np
import useq

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda._engine import MDAEngine


def test_slm_image():
    DEV = "slm"

    mmc = CMMCorePlus.instance()
    mmc.loadSystemConfiguration()
    mock_core = MagicMock(wraps=mmc)
    mock_core.getDeviceName.return_value = "Mosaic3"  # for device name lookup
    mock_core.setSLMPixelsTo.return_value = None
    mock_core.setSLMImage.return_value = None
    mock_core.displaySLMImage.return_value = None
    mmc.mda.set_engine(MDAEngine(mmc=mock_core))

    seq = useq.MDASequence(
        time_plan=useq.TIntervalLoops(interval=0, loops=2),
        channels=["DAPI", "FITC"],
    )

    # slm image from boolean True/False
    events = [x.replace(slm_image=useq.SLMImage(data=True, device=DEV)) for x in seq]
    mock_core.mda.run(events)
    assert mock_core.setSLMPixelsTo.call_count == len(events)
    # asserting called with 1 because that is the "on" value for Mosaic3 device
    # which we mocked above.
    mock_core.setSLMPixelsTo.assert_called_with(DEV, 1)
    mock_core.setSLMPixelsTo.reset_mock()

    events = [x.replace(slm_image=useq.SLMImage(data=False, device=DEV)) for x in seq]
    mock_core.mda.run(events)
    mock_core.setSLMPixelsTo.assert_called_with(DEV, 0)

    # regular image
    data = [[True, False], [True, False]]
    events = [x.replace(slm_image=useq.SLMImage(data=data, device=DEV)) for x in seq]
    mock_core.mda.run(events)
    assert mock_core.setSLMImage.call_count == len(events)
    call_device, call_data = mock_core.setSLMImage.call_args_list[-1][0]
    assert call_device == DEV
    np.testing.assert_array_equal(call_data, data)
    mock_core.displaySLMImage.assert_called_with(DEV)
    mock_core.displaySLMImage.call_count = len(events)

    # rgb image
    mock_core.displaySLMImage.reset_mock()
    mock_core.setSLMImage.reset_mock()
    data2 = [[1, 2, 3], [3, 4, 5]]
    events = [x.replace(slm_image=useq.SLMImage(data=data2, device=DEV)) for x in seq]
    mock_core.mda.run(events)
    call_device, call_data = mock_core.setSLMImage.call_args_list[-1][0]
    assert call_device == DEV
    np.testing.assert_array_equal(call_data, data2)
    mock_core.displaySLMImage.assert_called_with(DEV)

    # single rgb color
    mock_core.setSLMPixelsTo.reset_mock()
    events = [
        x.replace(slm_image=useq.SLMImage(data=(1, 2, 3), device=DEV)) for x in seq
    ]
    mock_core.mda.run(events)
    mock_core.setSLMPixelsTo.assert_called_with(DEV, 1, 2, 3)
