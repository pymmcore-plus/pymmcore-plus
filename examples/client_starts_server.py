import sys

from pymmcore_remote import RemoteMMCore

cleanup_new = "--leave-open" not in sys.argv
cleanup_existing = "--cleanup-existing" in sys.argv


with RemoteMMCore(cleanup_new=cleanup_new, cleanup_existing=cleanup_existing) as mmcore:
    mmcore.loadSystemConfiguration("demo")  # 'demo' is a special option for CMMCorePlus
    print("loaded:", mmcore.getLoadedDevices())
