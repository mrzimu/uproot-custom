from uproot_custom import registered_readers, AsCustom

from .OverrideStreamerReader import OverrideStreamerReader

AsCustom.target_branches |= {
    "/my_tree:override_streamer",
}

registered_readers.add(OverrideStreamerReader)
