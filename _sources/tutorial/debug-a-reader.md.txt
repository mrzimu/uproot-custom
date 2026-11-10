# Debug a reader

A Detree reader has two executors: the compiler's Python interpreter (`uproot_custom.detree.interp`) and the Detree machine (`uproot_custom.detree.run`). They run the same reader source, so a disagreement between them localizes a bug to the reader or to the compiler, and a reader that fails in both is a reader bug.

## Compile the reader without a file

Compile the reader directly to catch contract and subset errors before opening a file:

```python
from uproot_custom.detree.compiler.frontend import compile_reader, describe_reader
from uproot_custom.factories import TArrayFactory

reader = TArrayFactory(name="branch", dtype="int32").build_detree_reader()
print(describe_reader(reader))

raw, signature = compile_reader(reader)
```

Any factory works here; `TArrayFactory` is a built-in that needs no project. `describe_reader` returns the structural signature that keys the compilation cache, and `compile_reader` returns the module bytes and that signature, raising `UnsupportedNode` when the reader cannot be compiled.

## Compare the two executors

Run one basket under each executor and compare the buffers:

```python
import uproot

from uproot_custom.detree import interp
from uproot_custom.detree.run import read_data

f = uproot.open("file.root")
entry = f["/my_tree:my_branch"]
reader = entry.interpretation.factory.build_detree_reader()
basket = entry.basket(0)

interp.read_basket(reader, basket.data, basket.byte_offsets, basket.member("fKeylen"))
print(reader.data())

reader = entry.interpretation.factory.build_detree_reader()
print(read_data(reader, basket.data, basket.byte_offsets, basket.member("fKeylen")))
```

`interp` runs the reader methods as plain Python — `print`, `pdb`, and ordinary tracebacks work there — while `read_data` compiles and runs the same tree on the machine. For a fixed-width branch, `byte_offsets` is `None` and the call needs the fixed entry size instead, as `nbyte=`.

`entry.interpretation` has to be `AsCustom` for `.factory` to exist, so register the path before this page's snippets ([get started](../getting-started.md#step-2-register-the-branch)); otherwise Uproot hands you its own interpretation, which has no `factory`.

## Dump the compiled module

Set `UPROOT_CUSTOM_DETREE_DUMP_MODULES=1` to print the module's instructions each time a reader is compiled. The old name `UPROOT_CUSTOM_JIT_DUMP_MODULES` is still honoured.

A reader whose `read` is three operations — skip the `TObject` header, read an `int`, read a `double` — compiles to this:

```{code-block} console
0000: Ins(op=SKIP_TOBJECT, rd=0, ra=0, rb=0, imm1=0, imm2=0)
0001: Ins(op=READ_APPEND, rd=0, ra=0, rb=0, imm1=0, imm2=7)
0002: Ins(op=SREAD, rd=0, ra=0, rb=0, imm1=3, imm2=0)
0003: Ins(op=MOV, rd=2, ra=0, rb=0, imm1=0, imm2=0)
0004: Ins(op=CONST, rd=3, ra=0, rb=0, imm1=305419896, imm2=0)
0005: Ins(op=CMP_EQ, rd=1, ra=2, rb=3, imm1=0, imm2=0)
0006: Ins(op=ASSERT, rd=0, ra=1, rb=0, imm1=0, imm2=0)
0007: Ins(op=READ_APPEND, rd=0, ra=0, rb=0, imm1=1, imm2=10)
0008: Ins(op=RET, rd=0, ra=0, rb=0, imm1=0, imm2=0)
```

The dump is the compiler's output, not a specification: `imm2=7` and `imm2=10` are buffer slots, `imm1=305419896` is the mask `0x12345678` folded into a constant, and the `MOV`/`CMP_EQ`/`ASSERT` trio is the `assert mask == 0x12345678`. Read it to confirm that the reader compiled to what you meant — a missing read or a reordered field shows up here first.

## When to take the Python + C++ route

A construct the compiler rejects is a reader that cannot run on Detree, and there is no fallback. When the read path needs plain Python — a `try` around an optional header, a dictionary lookup, a call into another package — the branch belongs on the **Python + C++ route**: write the same reader as an `IReader` ([stage 1](../advanced/python-reader.md)) and port it to C++ ([stage 2](../advanced/cpp-reader.md)), because the Python half is too slow to ship.

Keeping the Detree reader alongside them is still useful: all the implementations share the byte layout and one factory, so a disagreement localizes the bug to the read path rather than to your understanding of the format. Do not confuse the two Python appearances, though — `uproot_custom.detree.interp` runs the *Detree reader's own methods* as Python for debugging, while the `python` backend runs a separate `IReader` implementation; see [choosing a technical route](../concepts/choosing-a-route.md#three-things-called-python).

## Common problems

| Symptom | Cause | Fix |
| ------- | ----- | --- |
| `NotImplementedError: ... does not implement build_detree_reader` | the factory has no `build_detree_reader` | add `build_detree_reader`, or take the Python + C++ route |
| `Unknown reader backend: ...` | bad `UPROOT_CUSTOM_READER_BACKEND` value | use `cpp`, `python`, or `detree` |
| `AssertionError: Only awkward arrays are supported` | `library="np"` or `"pd"` | read with the default awkward library |
| `ReaderContractError: ... source is not available; readers must live in a .py file` | the reader was defined in a notebook or REPL | move it into a module |
| `ReaderContractError: ... self.<name> is assigned ...` | a plain attribute is written in a read path | declare it as `State(<default>)` |
| `UnsupportedNode: ... line N: ...` | a construct outside the compilable subset | rewrite the read path, or take the Python + C++ route |
| arrays differ between backends | `data()` does not match `make_awkward_content` | compare the two executors as shown above |
| `detree.spec.errors.AssertionFailed: <message> function=... ip=... cursor=...` | an `assert` in the read path failed on the machine | the message is yours; `cursor` and `ip` say where the read stopped |
| `detree.spec.errors.InvalidByteCount` / `StreamUnderflow` / `ReadLengthMismatch` | the read is out of step with the bytes | compare against the raw bytes; check the field before the one that failed |

The full list of errors and where each is raised is in the [Detree reference](../reference/detree-dsl.md#errors).
