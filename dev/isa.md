# Reader JIT instruction set (ISA)

```{important}
**Status: draft (v0.1), implemented as the experimental `jit` backend.** The
bytecode described here runs in `uproot_custom/readers/jit/`, and is selectable
with `backend.use("jit")`; see `docs/reference/reader-backends.md`. The Python
VM is the reference implementation; there is no C++ VM yet, and the opcode
numbers, operand conventions and module format may still change.
```

This ISA is the contract between two components:

- a **frontend**, which turns a Python `Reader` class (or a builder) into a
  *module* of bytecode, and
- a **virtual machine**, which executes that module against a ROOT basket.

The frontend and the VM can each be written in Python or C++. The bytecode
itself is backend-neutral data.

---

## 1. Design decisions

| Decision | Choice | Rationale |
|---|---|---|
| Machine model | **Register machine** | Easy to validate and to fuse into superinstructions. |
| Module granularity | **One module per branch** | The whole reader tree for one branch is monomorphised, so sub-reader calls are static and configuration can be constant-folded. |
| Control flow | **Flat jumps** (`JMP` / `JZ` / `JNZ` / `BR_*`) | Simple VM; the frontend emits structured loops but lowers them to jumps. A structured `LOOP` opcode may be added later behind a version bump. |
| Value model | **64-bit slots** | Reader values are sizes, counts, tags and indices, all below `2^63`. `uint64` identifiers are passed through unchanged. |
| Integer semantics | 64-bit two's complement, wrapping | Matches the C++ VM; documented deviation from Python's arbitrary precision. |
| Boolean results | `0` / `1` | Comparisons and `bool(...)` produce `0`/`1`; boolean buffers store `uint8` values. |
| Floating point | **Pass-through only** | Readers copy `float32`/`float64` from the stream to buffers; no arithmetic is required. Float arithmetic opcodes are reserved but not implemented. |
| `READ_FIELDS` layouts | **Flat only** | A layout is a sequence of scalar/skip/fixed-array fields. Nested readers are expressed with `CALL` plus fine-grained opcodes. |
| Strings | **Interned ids** | A string lives in a run-local arena; a register carries its `u32` id, never the bytes. `-1` means "no string". |
| Buffer checks | **Always on** | Every stream access is bounds-checked; violations raise a Python exception instead of crashing the process. |

```{note}
Strings are ids into an arena seeded with the module's constants, in order, so
`STR_CONST rd, k` is the constant at index `k`. `SREAD_CSTR` interns what it
reads, which makes `STR_EQ` an id comparison and lets `AnyPointerReader` compare
class names with two instructions.
```

---

## 2. Architecture

```{mermaid}
flowchart LR
    reader["Python Reader class"] --> front["Frontend (AST analysis)"]
    front --> module["Module (bytecode + tables)"]
    module --> cache[("on-disk cache<br/>content hash")]
    module --> vm["VM (Python first, C++ later)"]
    vm --> buffers["typed buffers"]
    buffers --> ak["awkward arrays (Python)"]
```

The **module** is the unit of caching and distribution. It contains everything
the VM needs: code, buffer declarations, state declarations, string constants,
type layouts and the function table. It can be serialised to disk and keyed by
a content hash, so identical reader trees share one compiled module.

---

## 3. Module format

```text
magic        "UCIR"
isa_major    u16            # incompatible changes
isa_minor    u16            # backward-compatible additions
entry        u16            # function id executed once per event
regs_max     u16            # upper bound used for validation

buffers[]    { name, dtype:u8, kind:u8, init:i64 }
states[]     { name, init:i64 }
strings[]    [ ... ]        # class names and message templates
layouts[]    { id, fields: [ { kind, typecode, count, buffer_id } ] }
funcs[]      { id, name, arity:u8, reg_count:u16, code_off:u32, code_len:u32 }
code[]       Ins[]          # 12 bytes each in the executable form
lines[]      ip -> source line (optional, for errors and tracing)
```

- **`kind`** of a buffer is `DATA` (element storage), `OFFSETS` (int64 offsets,
  initialised with one `0`) or `COUNT` (int64 counters).
- **`arity`** is `0` for `read()` and `1` for `read_many(count)`,
  `read_until(end_pos)` and `read_many_memberwise(count)`.
- **`layouts`** are flat. `field.kind` is one of `SCALAR`, `SKIP`,
  `ARRAY_FIXED`, `TOBJECT_SKIP`.
- **One module per branch** means all reader instances of that branch share the
  id space: buffer ids, state slots and function ids are module-global.

### Deterministic identifiers

Ids are assigned by a deterministic traversal of the reader tree (root first,
then children in declaration order). They must **not** be derived from
`hash(obj)` or from branch names, so that two structurally identical branches
produce byte-identical modules and can be deduplicated by content hash.

---

## 4. Runtime model

```text
VM
├── regs[0..R)        64-bit slots, one window per call frame
├── frames            (func_id, return ip, return register)
├── stream            data[], entry_offsets[], cursor, initial_cursor, event_end
├── buffers[]         { dtype, kind, storage, count }
├── states[]          64-bit scalar state per reader instance
├── refs              map<u32, Ref{kind, object_index, class_name}>
└── strings           constant pool and runtime string arena
```

### Values

A register holds a 64-bit slot. Integer opcodes interpret it as signed or
unsigned; float values are stored as their IEEE-754 bit pattern and are only
moved, never computed on. The frontend statically knows the type of every
expression, but the VM does not need to track it.

### Buffers

Buffers are append-only during a run. `OFFSETS` buffers start with a single
`0` element, which makes `BUF_APPEND_OFFSET` a one-instruction update. After
`HALT`, each buffer is exposed to Python as a NumPy array with the declared
dtype.

### Reader state

`STATE_*` opcodes access scalar fields of a reader instance that must persist
across events (for example `object_counter` in `AnyPointerReader`).
Configuration values (`with_header`, `flat_size`, `dtype`) are **constants**
and are folded into the code or operands by the frontend.

---

## 5. Instruction encoding

The executable form is fixed-size for simplicity:

```cpp
struct Ins {
    uint8_t op;      // opcode
    uint8_t rd;      // destination register
    uint8_t ra;      // source register A
    uint8_t rb;      // source register B
    int32_t imm1;    // immediate / BUF / SLOT / FUNC / LAYOUT / MSG / TC
    int32_t imm2;    // jump target / second immediate / stride
};
```

Operand notation used below:

| Symbol | Meaning |
|---|---|
| `rd`, `ra`, `rb` | register numbers (0–255) |
| `IMM` | immediate value |
| `BUF` | buffer id |
| `TC` | typecode |
| `SLOT` | state slot id |
| `FUNC` | function id |
| `LBL` | absolute instruction index |
| `LAYOUT` | layout id |
| `MSG` | message id (index into `strings`) |
| `CONST` | string constant id |

A compact varint encoding for on-disk storage is planned; the semantics are
unchanged.

---

## 6. Instruction set

### 6.1 Control and constants

| Opcode | Hex | Operands | Semantics |
|---|---|---|---|
| `HALT` | 0x00 | — | Stop execution; the VM returns the buffers. |
| `NOP` | 0x01 | — | No operation. |
| `LINE` | 0x02 | `IMM` | Record the source line (debug only). |
| `DEBUG_PRINT` | 0x03 | `MSG`, `ra` | Print a debug message (disabled by default). |
| `CONST` | 0x10 | `rd`, `IMM` | `rd = IMM` (64-bit). |
| `CONST_F` | 0x11 | `rd`, `IMM` | `rd = double bits` (reserved for pass-through). |
| `MOV` | 0x12 | `rd`, `ra` | `rd = ra`. |
| `ZEXT32`/`ZEXT16`/`ZEXT8` | 0x13/0x15/0x17 | `rd`, `ra` | Zero-extend the low 32/16/8 bits. |
| `SEXT32`/`SEXT16`/`SEXT8` | 0x14/0x16/0x18 | `rd`, `ra` | Sign-extend the low 32/16/8 bits. |

### 6.2 Integer arithmetic

All operations wrap modulo `2^64`; division and modulo truncate toward zero,
matching C++.

| Opcode | Hex | Operands | Semantics |
|---|---|---|---|
| `ADD` | 0x20 | `rd`, `ra`, `rb` | `rd = ra + rb` |
| `SUB` | 0x21 | `rd`, `ra`, `rb` | `rd = ra - rb` |
| `MUL` | 0x22 | `rd`, `ra`, `rb` | `rd = ra * rb` |
| `DIV_S` | 0x23 | `rd`, `ra`, `rb` | signed division |
| `DIV_U` | 0x24 | `rd`, `ra`, `rb` | unsigned division |
| `MOD_S` | 0x25 | `rd`, `ra`, `rb` | signed remainder |
| `MOD_U` | 0x26 | `rd`, `ra`, `rb` | unsigned remainder |
| `NEG` | 0x27 | `rd`, `ra` | `rd = -ra` |
| `SHL` | 0x28 | `rd`, `ra`, `rb` | shift left |
| `SHR_S` | 0x29 | `rd`, `ra`, `rb` | arithmetic shift right |
| `SHR_U` | 0x2A | `rd`, `ra`, `rb` | logical shift right |
| `AND` | 0x2B | `rd`, `ra`, `rb` | bitwise and |
| `OR` | 0x2C | `rd`, `ra`, `rb` | bitwise or |
| `XOR` | 0x2D | `rd`, `ra`, `rb` | bitwise xor |
| `NOT` | 0x2E | `rd`, `ra` | bitwise complement |
| `NOT_B` | 0x2F | `rd`, `ra` | logical not, result `0`/`1` |

```{note}
Opcodes `0x30`–`0x3F` are reserved for float arithmetic
(`FADD`, `FSUB`, `FMUL`, `FDIV`, `FNEG`, `I2F`, `F2I`). They are **not
implemented in v0**: readers only move floats between the stream and buffers.
```

### 6.3 Comparison

Results are always `0` or `1`.

| Opcode | Hex | Operands | Semantics |
|---|---|---|---|
| `CMP_EQ` | 0x40 | `rd`, `ra`, `rb` | `ra == rb` |
| `CMP_NE` | 0x41 | `rd`, `ra`, `rb` | `ra != rb` |
| `CMP_LT_S` | 0x42 | `rd`, `ra`, `rb` | signed `ra < rb` |
| `CMP_LE_S` | 0x43 | `rd`, `ra`, `rb` | signed `ra <= rb` |
| `CMP_GT_S` | 0x44 | `rd`, `ra`, `rb` | signed `ra > rb` |
| `CMP_GE_S` | 0x45 | `rd`, `ra`, `rb` | signed `ra >= rb` |
| `CMP_LT_U` | 0x46 | `rd`, `ra`, `rb` | unsigned `ra < rb` |
| `CMP_LE_U` | 0x47 | `rd`, `ra`, `rb` | unsigned `ra <= rb` |
| `CMP_GT_U` | 0x48 | `rd`, `ra`, `rb` | unsigned `ra > rb` |
| `CMP_GE_U` | 0x49 | `rd`, `ra`, `rb` | unsigned `ra >= rb` |

### 6.4 Control flow

| Opcode | Hex | Operands | Semantics |
|---|---|---|---|
| `JMP` | 0x50 | `LBL` | Unconditional jump. |
| `JZ` | 0x51 | `ra`, `LBL` | Jump if `ra == 0`. |
| `JNZ` | 0x52 | `ra`, `LBL` | Jump if `ra != 0`. |
| `BR_EQ` | 0x53 | `ra`, `rb`, `LBL` | Jump if `ra == rb`. |
| `BR_NE` | 0x54 | `ra`, `rb`, `LBL` | Jump if `ra != rb`. |
| `BR_LT_S` | 0x55 | `ra`, `rb`, `LBL` | signed less-than branch. |
| `BR_LE_S` | 0x56 | `ra`, `rb`, `LBL` | signed less-or-equal branch. |
| `BR_GT_S` | 0x57 | `ra`, `rb`, `LBL` | signed greater-than branch. |
| `BR_GE_S` | 0x58 | `ra`, `rb`, `LBL` | signed greater-or-equal branch. |
| `BR_LT_U`/`BR_LE_U`/`BR_GT_U`/`BR_GE_U` | 0x59–0x5C | `ra`, `rb`, `LBL` | unsigned variants. |
| `CALL` | 0x5D | `rd`, `FUNC`, `ra` | Call `FUNC` with argument `ra`; result in `rd`. |
| `RET` | 0x5E | `ra` | Return `ra` to the caller. |

The fused `BR_*` opcodes are a performance tier: `CMP_*` followed by `JZ`/`JNZ`
is equivalent but costs one more dispatch.

### 6.5 Stream access

Every access is bounds-checked against the current event's data. Violations
raise `StreamUnderflow` / `ReadLengthMismatch`.

| Opcode | Hex | Operands | Semantics |
|---|---|---|---|
| `SREAD` | 0x60 | `rd`, `TC` | Read one big-endian scalar of type `TC`. |
| `SREAD_FNB` | 0x61 | `rd` | Read `fNBytes`, validate the byte-count mask, return the masked value. |
| `SREAD_VERSION` | 0x62 | `rd` | Read the int16 `fVersion`. |
| `SREAD_CSTR` | 0x63 | `rd` | Read a NUL-terminated string and intern it; `rd` gets its arena id. |
| `SREAD_TSTRING` | 0x64 | `rd`, `BUF` | Read a `TString` into a byte buffer (reserved). |
| `SKIP` | 0x65 | `IMM` | Advance the cursor by a constant. |
| `SKIP_R` | 0x66 | `ra` | Advance the cursor by a register value. |
| `SKIP_FNB` | 0x67 | — | Skip `fNBytes` (still validating the mask). |
| `SKIP_VERSION` | 0x68 | — | Skip 2 bytes. |
| `SKIP_TOBJECT` | 0x69 | — | Skip a `TObject` header. |
| `SKIP_OBJHDR` | 0x6A | — | Skip `fNBytes` + tag (+ class name if new). |
| `SKIP_CSTR` | 0x6B | — | Skip a NUL-terminated string. |
| `CURSOR` | 0x6C | `rd` | `rd = cursor`. |
| `SET_CURSOR` | 0x6D | `ra` | `cursor = ra` (bounds-checked). |
| `ENTRIES` | 0x6E | `rd` | Number of events in the basket. |
| `INIT_OFFSET` | 0x6F | `rd` | `initial_cursor_position` of the stream. |
| `DATA_SIZE` | 0x70 | `rd` | Size of the current event's data. |

### 6.6 Event offsets

| Opcode | Hex | Operands | Semantics |
|---|---|---|---|
| `OFFSET_AT` | 0x71 | `rd`, `ra` | `rd = entry_offsets[ra]`. |
| `OFFSET_SEEK` | 0x72 | `rd`, `ra` | Smallest entry offset strictly greater than `ra`. |
| `EVENT_END` | 0x73 | `rd` | `rd = entry_offsets[event + 1]`. |

`OFFSET_SEEK` replaces the only NumPy operation in the current reader code
(`CStyleArrayReader` searching for the end of a jagged array).

### 6.7 Coarse-grained reads

These are the performance tier. The dense variants must run a native loop
inside the VM rather than dispatching per element.

| Opcode | Hex | Operands | Semantics |
|---|---|---|---|
| `READ_BULK` | 0x78 | `BUF`, `TC`, `ra` | Read `ra` consecutive elements into `BUF`. |
| `READ_STRIDED` | 0x79 | `BUF`, `TC`, `ra`, `rb` | Read `ra` elements spaced by `rb` bytes into `BUF`. |
| `READ_FIELDS` | 0x7A | `LAYOUT`, `ra` | Read `ra` flat objects of a layout into their buffers. |
| `READ_APPEND` | 0x7B | `BUF`, `TC` | Read one element and append it (fusion of `SREAD` + `BUF_APPEND`). |

### 6.8 Buffer access

| Opcode | Hex | Operands | Semantics |
|---|---|---|---|
| `BUF_APPEND` | 0x80 | `BUF`, `ra` | `BUF.append(ra)`. |
| `BUF_APPEND_CONST` | 0x81 | `BUF`, `IMM` | Append a constant. |
| `BUF_APPEND_OFFSET` | 0x82 | `BUF`, `ra` | `BUF.append(BUF[-1] + ra)`. |
| `BUF_APPEND_LEN` | 0x83 | `BUF`, `BUF` | `dst.append(len(src))`. |
| `BUF_LAST` | 0x84 | `rd`, `BUF` | `rd = BUF[-1]`. |
| `BUF_LEN` | 0x85 | `rd`, `BUF` | `rd = len(BUF)`. |
| `BUF_RESERVE` | 0x86 | `BUF`, `ra` | Reserve capacity (a hint; may be a no-op). |

### 6.9 Reader state

| Opcode | Hex | Operands | Semantics |
|---|---|---|---|
| `STATE_GET` | 0x88 | `rd`, `SLOT` | `rd = states[SLOT]`. |
| `STATE_SET` | 0x89 | `SLOT`, `ra` | `states[SLOT] = ra`. |
| `STATE_IADD` | 0x8A | `SLOT`, `IMM` | `states[SLOT] += IMM`. |

### 6.10 Object references

Used by `AnyPointerReader`. The Python `dict` of `_Reference` objects is
replaced by these opcodes so that the DSL never sees a container type.

| Opcode | Hex | Operands | Semantics |
|---|---|---|---|
| `REF_HAS` | 0x90 | `rd`, `ra` | `rd = (tag in refs)`. |
| `REF_GET_OBJ` | 0x91 | `rd`, `ra` | Object index of a reference. |
| `REF_GET_CLASS` | 0x92 | `rd`, `ra` | Class-name id of a reference, `-1` when it has none. |
| `REF_SET_OBJ` | 0x93 | `ra`, `rb` | Store an object reference. |
| `REF_SET_CLASS` | 0x94 | `ra`, `rb` | Store a class reference. |
| `REF_COUNT` | 0x95 | `rd` | Number of entries. |

### 6.11 Strings

Allocated but **not implemented in v0**; executing any of them raises
`UnsupportedFeature`.

| Opcode | Hex | Operands | Semantics |
|---|---|---|---|
| `STR_CONST` | 0x98 | `rd`, `CONST` | Load an interned constant string. |
| `STR_EQ` | 0x99 | `rd`, `ra`, `rb` | String equality, result `0`/`1`. |
| `STR_STORE` | 0x9A | `SLOT`, `ra` | Store a string in reader state. |
| `STR_LOAD` | 0x9B | `rd`, `SLOT` | Load a string from reader state. |

### 6.12 Verification and errors

| Opcode | Hex | Operands | Semantics |
|---|---|---|---|
| `ASSERT` | 0xA0 | `ra`, `MSG` | Fail unless `ra != 0`. |
| `ASSERT_CURSOR_EQ` | 0xA1 | `ra`, `MSG` | Fail unless `cursor == ra`. |
| `ASSERT_STR_EQ` | 0xA2 | `ra`, `rb`, `MSG` | Fail unless the strings are equal. |
| `THROW` | 0xA3 | `MSG` | Raise an unconditional reader error. |

---

## 7. Call convention

- Every reader instance exposes up to four functions:
  `read()` (arity 0), `read_many(count)`, `read_until(end_pos)` and
  `read_many_memberwise(count)` (arity 1).
- `CALL rd, FUNC, ra` passes `ra` as the argument and stores the return value in
  `rd`. A callee has its own register window; `RET ra` returns `ra`.
- Default implementations may be generated by the frontend when a reader does
  not override them: `read_many` and `read_until` are loops over `read`.
- Statically known leaf readers should be inlined by the frontend. `CALL` is
  reserved for recursive structures, pointer graphs and member-wise dispatch.
- Helper methods on a reader (for example `read_body`) become ordinary
  functions with arity 0 or 1. Methods must not return tuples in the JIT path.

---

## 8. Event loop

The VM owns the per-basket loop; bytecode never sees it:

```text
cursor = 0
for event in range(entries):
    event_end = entry_offsets[event + 1]
    call entry_function
    if cursor != event_end: raise ReadLengthMismatch
```

This keeps the Python/C++ boundary at one call per basket and lets each event
be checked independently.

---

## 9. Mapping from the Python reader API

| Python | Opcode(s) |
|---|---|
| `stream.read_uint32()` | `SREAD rd, I` |
| `stream.read_int16()` | `SREAD rd, h` |
| `stream.read_float()` / `read_double()` | `SREAD rd, f` / `SREAD rd, d` |
| `stream.read_fNBytes()` | `SREAD_FNB rd` |
| `stream.read_fVersion()` | `SREAD_VERSION rd` |
| `stream.read_null_terminated_string()` | `SREAD_CSTR rd` |
| `stream.skip(n)` | `SKIP n` |
| `stream.skip_fNBytes()` | `SKIP_FNB` |
| `stream.skip_fVersion()` | `SKIP_VERSION` |
| `stream.skip_TObject()` | `SKIP_TOBJECT` |
| `stream.skip_null_terminated_string()` | `SKIP_CSTR` |
| `stream.cursor` / `stream.cursor = x` | `CURSOR rd` / `SET_CURSOR ra` |
| `stream.entries` | `ENTRIES rd` |
| `stream.initial_cursor_position` | `INIT_OFFSET rd` |
| `stream.next_offset_after(pos)` | `OFFSET_SEEK rd, ra` |
| `stream.offsets[i]` | `OFFSET_AT rd, ra` |
| `tag in stream.refs` | `REF_HAS rd, ra` |
| `stream.refs.get_object(tag)` | `REF_GET_OBJ rd, ra` |
| `stream.refs.set_object(tag, idx)` | `REF_SET_OBJ ra, rb` |
| `stream.refs.count()` | `REF_COUNT rd` |
| `buf.append(v)` | `BUF_APPEND BUF, ra` |
| `buf.append(buf[-1] + n)` | `BUF_APPEND_OFFSET BUF, ra` |
| `len(buf)` | `BUF_LEN rd, BUF` |
| `buf[-1]` | `BUF_LAST rd, BUF` |
| `self.object_counter += 1` | `STATE_IADD SLOT, 1` |
| `self.with_header` (constant) | constant operand / folded branch |
| `if cond:` | `JZ cond, else` |
| `for _ in range(n): body` | `CONST i,0; L: BR_GE_S i,n,end; body; ADD i,i,1; JMP L` |
| `while stream.cursor < end:` | `L: CURSOR r; BR_GE_S r,end,end; body; JMP L` |
| `self.read(stream)` | `CALL rd, FUNC_read` |
| `self.child.read_many(stream, n)` | `CALL rd, FUNC_read_many, n` |
| `assert stream.cursor == end_pos` | `ASSERT_CURSOR_EQ end, MSG` |
| `raise NotImplementedError` | `THROW MSG` |

`min`, `max`, `len`, `bool`, `int` and integer/bitwise operators are covered by
the arithmetic and comparison opcodes. NumPy and `dict` operations are **not**
part of the ISA.

---

## 10. Worked examples

### 10.1 `PrimitiveReader`

```python
def read(self, stream):
    self._data.append(stream.read_scalar(self.dtype))
```

```text
func Prim.read:
  SREAD      r0, TC
  BUF_APPEND data, r0
  RET
```

### 10.2 `TArrayReader`

```python
def read(self, stream):
    fSize = stream.read_uint32()
    self.offsets.append(self.offsets[-1] + fSize)
    for _ in range(fSize):
        self._data.append(stream.read_scalar(self.dtype))
```

Without fusion:

```text
  SREAD              r0, I
  BUF_APPEND_OFFSET  offsets, r0
  CONST              r1, 0
L:
  BR_GE_S            r1, r0, END
  SREAD              r2, TC
  BUF_APPEND         data, r2
  ADD                r1, r1, 1
  JMP                L
END:
  RET
```

With the counted-loop fusion:

```text
  SREAD              r0, I
  BUF_APPEND_OFFSET  offsets, r0
  READ_BULK          data, TC, r0
  RET
```

### 10.3 `TObjectReader` (`keep_data = True`)

```text
  SKIP_VERSION
  SREAD          r0, i          ; fUniqueID
  SREAD          r1, I          ; fBits
  CONST          r2, 0x10       ; kIsReferenced
  AND            r3, r1, r2
  JZ             r3, L1
  SREAD          r4, H
  BUF_APPEND     pidf, r4
L1:
  BUF_APPEND     unique_id, r0
  BUF_APPEND     bits, r1
  BUF_LEN        r5, pidf
  BUF_APPEND     pidf_offsets, r5
  RET
```

### 10.4 `STLSeqReader`

```text
func STLSeq.read:
  SKIP_FNB
  SREAD_VERSION  r0
  CONST          r1, 0x4000
  AND            r2, r0, r1
  JZ             r2, L_body
  CALL           r3, func[read_element_version]
L_body:
  CALL           r4, func[read_body], r2
  RET
```

The element reader is called through `CALL` with the count in `r4`'s argument
register. If the element is a primitive reader, the frontend may inline it and
emit `READ_BULK` directly.

### 10.5 `CStyleArrayReader` (jagged branch)

```text
  CURSOR         r0
  OFFSET_SEEK    r1, r0
  CALL           r2, func[element.read_until], r1
  BUF_APPEND_OFFSET offsets, r2
  RET
```

---

## 11. Validation and errors

The VM validates a module before execution:

- every register index is below the owning function's `reg_count`;
- every jump target lies inside the owning function;
- every referenced `BUF`, `SLOT`, `FUNC`, `LAYOUT`, `CONST` and `MSG` exists;
- every typecode is known;
- `entry` refers to an existing function;
- `isa_major` matches the VM.

Runtime errors carry the instruction index, the source line (when available),
the cursor position and the byte offset. The error types are:

| Error | Raised when |
|---|---|
| `StreamUnderflow` | a read or skip would leave the event's data. |
| `InvalidByteCount` | `fNBytes` lacks `kByteCountMask`. |
| `ReadLengthMismatch` | the cursor is not at the event boundary after `read`. |
| `UnsupportedFeature` | a reserved opcode (float arithmetic, `SREAD_TSTRING`) is executed. |
| `AssertionFailed` | an `ASSERT*` opcode fails. |
| `StackOverflow` | the call depth limit is exceeded. |

---

## 12. Performance guidance

The VM's cost is dominated by dispatch frequency, so the frontend must keep hot
loops inside coarse opcodes:

| Pattern | Required opcode | Target |
|---|---|---|
| scalar arrays, `vector<primitive>` | `READ_BULK` | ≤ 1.5 ns/element |
| arrays of flat structs | `READ_FIELDS` | ≤ 2 ns/element |
| offset bookkeeping | `BUF_APPEND_OFFSET` | one instruction per element |
| single-element hot path | `READ_APPEND` | ≤ 2 ns/element |
| loop control | fused `BR_*` | one dispatch per iteration |
| buffer growth | `BUF_RESERVE` | avoid geometric reallocation |

A reader that executes three or more opcodes per element will be several times
slower than the current C++ reader graph. The frontend's fusion pass exists to
prevent this for the canonical patterns listed in
[Reader JIT refactor plan](reader-jit-refactor.md).

---

## 13. v0 scope

**Implemented in v0**

- register machine, 64-bit integer semantics, comparisons returning `0`/`1`;
- `READ_BULK`, `READ_STRIDED`, `READ_FIELDS`, `READ_APPEND`;
- buffers (`DATA`, `OFFSETS`, `COUNT`), reader state, `OFFSET_SEEK`;
- string arena and the `STR_*` / `ASSERT_STR_EQ` / `SREAD_CSTR` opcodes, and the
  full `REF_*` set, which is what `AnyPointerReader` needs;
- flat control flow and fused branches;
- one module per branch, content-hash caching, deterministic ids;
- all 12 built-in readers.

**Deferred**

- float arithmetic opcodes (readers only move floats);
- `SREAD_TSTRING` (readers walk the bytes with `SREAD`/`READ_BULK` instead);
- a structured `LOOP` opcode (flat jumps only for now);
- a compact serialization format;
- the C++ VM (the Python VM is the reference implementation first).

---

## 14. Open questions

1. **`READ_FIELDS` fast path scope.** Only flat layouts are supported; classes
   with nested containers or custom sub-readers go through `CALL`.
2. **Module deduplication.** With one module per branch, identical branches are
   deduplicated by content hash. This requires strictly deterministic ids and
   code generation.
3. **Register allocation.** The frontend may use a simple linear-scan allocator;
   the VM only needs `reg_count` per function.
4. **Cache location and invalidation.** Suggested key: hash of the generated
   module bytes, versioned by `isa_major`/`isa_minor` and the package version.
5. **Debugging.** A Python reference VM with instruction-level tracing is
   planned; the C++ VM will be validated against it.
