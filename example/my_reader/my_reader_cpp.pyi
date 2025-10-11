from uproot_custom.cpp import IElementReader

class OverrideStreamerReader(IElementReader):
    def __init__(self, name: str): ...

class TObjArrayReader(IElementReader):
    def __init__(
        self,
        name: str,
        element_reader: IElementReader,
    ): ...
