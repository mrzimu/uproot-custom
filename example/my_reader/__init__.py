from uproot_custom import registered_factories, AsCustom

from .OverrideStreamerFactory import OverrideStreamerFactory
from .TObjArrayFactory import TObjArrayFactory

AsCustom.target_branches |= {
    "/my_tree:override_streamer",
    "/my_tree:obj_with_obj_array/m_obj_array",
}

registered_factories.add(OverrideStreamerFactory)
registered_factories.add(TObjArrayFactory)
