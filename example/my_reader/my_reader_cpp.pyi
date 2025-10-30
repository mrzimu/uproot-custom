from uproot_custom.cpp import IReader

class OverrideStreamerReader(IReader):
    def __init__(self, name: str): ...

class TObjArrayReader(IReader):
    def __init__(
        self,
        name: str,
        element_reader: IReader,
    ): ...
