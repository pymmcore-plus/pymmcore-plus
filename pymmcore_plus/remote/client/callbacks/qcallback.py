from Pyro5.api import expose
from qtpy.QtCore import Signal

from ....core.events import _qsignals


class QCoreSignaler(_qsignals.QCoreSignaler):
    # not sure why, but this seems to need to be here for the order of emission test.
    frameReady = Signal(object, object)

    @expose
    def receive_core_callback(self, signal_name, args):
        # let it throw an exception.
        getattr(self, signal_name).emit(*args)
