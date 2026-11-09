# Reader JIT refactor plan

```{important}
**Status: partially implemented.** Phase 0 (module format, validator, Python VM,
builder) and a frontend for the built-in constructs are implemented in
`uproot_custom/readers/jit/`, and are selectable with `backend.use("jit")`.

What exists today differs from the plan below in one place: instead of
translating the existing `Reader` classes (items R1--R9), the JIT stack has its
own `Node` classes that merge factory and reader -- structure declaration,
bytecode generation and awkward reconstruction in one object -- and its own
`build_node` that turns streamer information into that tree. The existing
`Reader` and `Factory` classes are untouched and serve as the oracle of the
differential tests.

Still open: the AST frontend for *user-written* readers (R1--R9 and `declare_*`),
the C++ VM and an on-disk module cache. `AnyPointerReader` is covered -- the
string and reference opcodes are implemented -- so all twelve built-in readers
compile. A branch whose tree contains something the frontend has no node for
still falls back to the Python reader tree.
```

## 1. Goal

Today a user who wants a fast custom reader must write the logic twice: once in
Python (for development) and once in C++ (for production), then build a pybind11
extension. The C++ step is a distribution barrier: downstream packages need a
C++17 toolchain and CMake, and any change requires rebuilding.

The JIT plan removes that step:

```text
user writes one Python Reader
        │
        ├── Python backend  (reference interpreter, always works)
        └── JIT frontend → bytecode → VM (fast, no C++ toolchain)
```

The Python backend remains the source of truth and the fallback. The JIT is an
optional accelerator selected per branch.

## 2. Why the readers need adaptation

The current readers are ordinary Python objects. Most of the read logic maps
cleanly to the ISA, but a few patterns are hard or impossible to translate:

| Current pattern | Problem |
|---|---|
| `self._data = array("B")` | buffer dtype and kind are implicit; a frontend would have to inspect `array` typecodes |
| `self.buffer_reader = DTYPE_TO_READER[dtype]` then `self.buffer_reader(stream)` | stores a bound method; the call target cannot be resolved statically |
| `stream.refs[tag].object_index`, `_Reference(...)` | Python `dict` plus a dataclass plus a union; no ISA equivalent |
| `(entry_offsets > cursor).nonzero()[0].min()` | NumPy operation inside the read path |
| `assert ... f"...{self.name}..."` | f-string message cannot be evaluated at compile time |
| `hash(self)` used to build reader ids | non-deterministic across processes, which breaks content-hash caching |
| sub-readers discovered as arbitrary attributes | traversal order is not guaranteed |

The adaptation is therefore **mostly declarative**: make existing information
explicit, and replace a handful of non-mappable expressions with named
primitives. The reading logic itself stays the same.

## 3. Principles

1. **Explicit declarations.** Buffers, scalar state, compile-time constants and
   sub-readers are declared through the base class, not inferred from arbitrary
   Python.
2. **Mappable primitives.** The read path only uses operations with a 1:1
   opcode mapping. NumPy, `dict`, dataclasses and dynamic messages move behind
   named methods.
3. **Deterministic identifiers.** Ids come from a deterministic traversal, never
   from `hash(obj)` or branch names, so identical branches produce identical
   modules.
4. **`data()` is untouched.** It still builds arrays from `np.asarray(buf)`; the
   Python backend supplies `array.array` buffers and the VM supplies NumPy
   arrays, which `np.asarray` accepts in both cases.
5. **Graceful fallback.** If a reader does not follow the rules, the frontend
   reports it once and the branch uses the Python backend. Correctness is never
   sacrificed for speed.

## 4. Refactor items

Each item shows the current code and the adapted code.

### R1. Declare buffers, state, constants and sub-readers

```python
# before
self.with_header = with_header
self.element_reader = element_reader
self.offsets = array("q", [0])
self._data = array("B")
```

```python
# after
self.with_header    = self.declare_const("with_header", with_header)
self.element_reader = self.declare_reader("element", element_reader)
self.offsets        = self.declare_buffer("offsets", "int64", kind=OFFSETS)
self._data          = self.declare_buffer("data", "uint8")
```

The frontend reads the declarations directly; no type inference over `array`
calls is needed. `declare_const` distinguishes values that can be folded from
mutable `declare_state` slots.

### R2. Read scalars through an explicit primitive

```python
# before — indirect call through a stored bound method
self.buffer_reader = DTYPE_TO_READER[dtype]
self._data.append(self.buffer_reader(stream))
```

```python
# after
self.dtype = self.declare_const("dtype", dtype)
self._data.append(stream.read_scalar(self.dtype))
```

`stream.read_scalar(TC)` maps to `SREAD rd, TC`. Because `dtype` is a declared
constant, the typecode is known at compile time.

### R3. Replace the `refs` dictionary with named methods

```python
# before
idx = stream.refs[fTag].object_index
if fTag not in stream.refs: ...
stream.refs[key] = _Reference(type="object", object_index=n)
len(stream.refs)
```

```python
# after
idx = stream.refs.get_object(fTag)
if not stream.refs.has(fTag): ...
stream.refs.set_object(key, n)
stream.refs.count()
```

Maps to `REF_*` opcodes. The DSL never sees a container type or a union.

### R4. Replace the NumPy offset search with a named primitive

```python
# before
end_offset_index = (entry_offsets > cursor_pos).nonzero()[0].min()
end_pos = entry_offsets[end_offset_index]
```

```python
# after
end_pos = stream.next_offset_after(stream.cursor)
```

Maps to a single `OFFSET_SEEK`. This was the only NumPy operation in the read
path.

### R5. Replace f-string assertions with named checks

```python
# before
assert stream.cursor == end_pos, (
    f"{self.__class__.__name__}({self.name}): Invalid read length! "
    f"Expect {fNBytes} bytes, but read {stream.cursor - start_pos} bytes."
)
```

```python
# after
stream.expect_end(end_pos, "AnyClass")
```

Maps to `ASSERT_CURSOR_EQ end_pos, MSG`. The message is a constant id plus a
source line, resolved by the VM.

### R6. Route string comparisons through methods (frontend work)

```python
# after
name = stream.read_cstr()                  # SREAD_CSTR -> arena id
self.check_class_name(name)                # STR_EQ + ASSERT_STR_EQ
```

The string and reference opcodes exist ([the ISA](isa.md) sections 6.10 and
6.11), and `AnyPointerReader` is compiled from them. What is still missing is
the item itself: the AST frontend that recognises this shape in a user's
reader. Hand-written nodes do it today; see `nodes/anypointer.py`.

### R7. Sub-reader lists must be declared and immutable

```python
# after
self.element_readers = self.declare_readers("elements", [r0, r1, r2])
...
for reader in self.element_readers:        # unrolled at compile time
    reader.read(stream)
```

Only `for reader in self.<declared_reader_list>` is supported; the list is a
tuple and is unrolled into one `CALL` per element. Lists that change at runtime
are not translatable.

### R8. No tuple or multi-value returns from read helpers

```python
# before
def read_element_version(self, stream):
    version = stream.read_fVersion()
    checksum = None
    if version == 0:
        checksum = stream.read_uint32()
    return version, checksum      # callers ignore it
```

```python
# after
def read_element_version(self, stream) -> None:
    if stream.read_fVersion() == 0:
        stream.skip(4)
```

`CALL` has exactly one return value. Helper methods with arity 0 or 1 are fine;
tuples are not.

### R9. Deterministic ids and traversal

```python
# before (readers/_forth.py)
obj_hash = str(hash(self))
for i in range(10):
    obj_hash = obj_hash.replace(str(i), chr(ord("a") + i))
```

```python
# after
# ids are assigned by traversal order: root = 0, then children in declaration
# order; or derived from a stable path such as "root.element"
def children(self) -> tuple[IReader, ...]: ...
```

Deterministic ids are what make one-module-per-branch caching work: two
structurally identical branches must produce byte-identical modules, which are
then deduplicated by content hash.

## 5. Base-class API

```python
class IReader:
    # declarations, called from __init__
    def declare_buffer(self, name, dtype, kind=DATA) -> Buffer
    def declare_state(self, name, init=0) -> int
    def declare_const(self, name, value) -> Const
    def declare_reader(self, name, reader) -> IReader
    def declare_readers(self, name, readers) -> tuple[IReader, ...]
    def children(self) -> tuple[IReader, ...]

    # default methods; the frontend may generate these bodies instead
    def read(self, stream): ...
    def read_many(self, stream, count):
        for _ in range(count):
            self.read(stream)
        return count
    def read_until(self, stream, end_pos):
        count = 0
        while stream.cursor < end_pos:
            self.read(stream)
            count += 1
        return count
    def read_many_memberwise(self, stream, count): ...

    # unchanged; runs in Python on both backends
    def data(self): ...
```

```python
class BinaryStream:
    # scalar reads -> SREAD
    def read_scalar(self, dtype)
    def read_fNBytes(self); def read_fVersion(self)
    # skips -> SKIP*
    def skip(self, n); def skip_fNBytes(self); def skip_fVersion(self)
    def skip_TObject(self)
    # stream state -> CURSOR / SET_CURSOR / ENTRIES / INIT_OFFSET
    cursor: int
    entries: int
    initial_cursor_position: int
    def next_offset_after(self, pos) -> int
    refs: Refs
    # explicit coarse-grained helpers (optional, map directly to READ_*)
    def read_bulk(self, buf, dtype, count)
    def read_strided(self, buf, dtype, stride, count)
```

Keep the `declare_*` defaults as no-ops returning the original object, so
third-party readers written against the old API still run on the Python backend.

## 6. Canonical patterns and fusion rules

The frontend's fusion pass recognises these forms and replaces them with coarse
opcodes. They are also the recommended way to write new readers.

| Canonical Python | Emitted opcode |
|---|---|
| `for _ in range(n): buf.append(stream.read_scalar(tc))` | `READ_BULK buf, tc, n` |
| `buf.append(stream.read_scalar(tc))` | `READ_APPEND buf, tc` |
| `buf.append(buf[-1] + x)` | `BUF_APPEND_OFFSET buf, x` |
| `for _ in range(n): <flat field sequence>` | `READ_FIELDS layout, n` |
| `buf.append(len(src))` | `BUF_APPEND_LEN buf, src` |
| `if (cmp): ...` | `BR_*` fused compare-and-branch |

```{note}
Fusion only applies to the exact canonical forms. A user reader that writes an
unusual loop still compiles, but falls back to the fine-grained opcodes and is
correspondingly slower. The frontend should warn when a hot loop is not fused.
```

## 7. Unsupported patterns

The frontend reports these and the branch falls back to the Python backend:

- storing and calling bound methods (`self.buffer_reader`);
- `getattr` / `setattr`, `**kwargs`, decorators;
- `try` / `except`, comprehensions, lambdas, generators in the read path;
- NumPy, `dict`, `set` or `isinstance` in the read path;
- f-string assertions or dynamically constructed messages;
- runtime iteration over lists or dicts of readers (only declared, immutable
  reader lists are supported);
- reading `self.<attr>` without a declaration;
- non-deterministic ids.

## 8. Rollout

### Phase 0 — Python virtual machine first

**Build the VM in Python before writing any C++.** The Python VM is the
reference implementation. It is slower than the eventual C++ VM, but it:

- has no build step, so the ISA and the frontend can be iterated quickly;
- can trace every instruction, which makes ISA bugs and frontend bugs obvious;
- serves as the oracle for differential testing against the Python backend;
- proves the module format and the caching story before they are frozen.

Phase 0 deliverables:

1. the module data structures and a validator;
2. a Python VM implementing the v0 opcode set;
3. a builder API to construct modules by hand;
4. unit tests for arithmetic, control flow, buffers, offsets and coarse reads.

Performance is explicitly not a goal in this phase.

### Phase 1 — adapt the readers and add the frontend

- implement R1–R9 on `readers/python.py`, keeping the Python backend passing;
- implement the AST frontend and the fusion pass;
- add per-branch module generation, deterministic ids and content-hash caching;
- differential tests: `python` backend vs Python VM, element by element.

### Phase 2 — migrate the VM to C++

Only after the ISA, the frontend and the test suite are stable:

- port the VM to C++ using the same bytecode and the same module format;
- run the C++ VM against the Python VM on every fixture (the Python VM is the
  oracle);
- benchmark against the current C++ reader graph and enforce the targets in
  [the ISA](isa.md).

The migration is mechanical because the bytecode is backend-neutral. No reader
code changes.

### Phase 3 — deferred features

- float arithmetic, only if a reader ever needs it;
- `SREAD_TSTRING` (readers walk the bytes instead);
- an optional structured `LOOP` opcode, if profiling shows it helps;
- a compact serialization format and a precompiled built-in module cache.

## 9. Testing strategy

| Level | What is checked |
|---|---|
| VM unit tests | each opcode, wrapping arithmetic, bounds checks, error types |
| Module validation | bad register/typecode/jump targets are rejected |
| Builder round-trip | `Module.to_dict()` / `from_dict()` reproduce the code |
| Differential | for every fixture: Python backend output == Python VM output |
| Fusion | fused and unfused modules produce identical buffers |
| Determinism | generating the same branch twice yields identical module bytes |
| Cache | second process loads the module without regenerating it |

The existing `tests/data/` ROOT files and the `backend.use(...)` context manager
already provide the differential harness; the new backend only needs to plug
into `read_branch_with_factory`.

## 10. Risks

| Risk | Mitigation |
|---|---|
| ISA churn after modules are cached | version the module format; reject `isa_major` mismatches |
| Frontend complexity grows with user code | strict subset plus automatic fallback; the Python backend is always correct |
| Fusion misses a hot loop | warn when a loop over a declared buffer is not fused; document canonical forms |
| Python VM is too slow for real use | it is a development tool; production remains the C++ backend until the C++ VM lands |
| Reader refactor breaks third-party readers | `declare_*` defaults are no-ops; old readers keep working on the Python backend |

## 11. Open items

1. Whether `declare_*` should be mandatory in a future major version.
2. Where generated modules are cached, and how they are invalidated.
3. The exact split between frontend inlining and `CALL` for sub-readers.
4. Whether helper methods such as `read_body` are emitted as functions or
   inlined by the frontend.
