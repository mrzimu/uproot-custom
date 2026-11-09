# Reader JIT 指令集（ISA）

> 本文是 [`isa.md`](isa.md) 的中文译本，内容与原文一一对应；如有歧义，以英文原文为准。

```{important}
**状态：草案（v0.1），以实验性的 `jit` 后端实现。** 这里描述的字节码运行在
`uproot_custom/readers/jit/` 中，可通过 `backend.use("jit")` 选用；
参见 `docs/reference/reader-backends.md`。Python 虚拟机是参考实现；目前还没有
C++ 虚拟机，操作码编号、操作数约定和模块格式仍可能变化。
```

本 ISA 是两个组件之间的契约：

- **前端**：把 Python 的 `Reader` 类（或某个 builder）转成一个字节码*模块*；
- **虚拟机**：针对一个 ROOT basket 执行该模块。

前端和虚拟机都可以用 Python 或 C++ 编写。字节码本身是与后端无关的数据。

---

## 1. 设计决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| 机器模型 | **寄存器机** | 易于验证，也易于融合成超指令（superinstruction）。 |
| 模块粒度 | **每个分支一个模块** | 一个分支的整棵 reader 树被单态化（monomorphised），因此子 reader 调用是静态的，配置可以被常量折叠。 |
| 控制流 | **扁平跳转**（`JMP` / `JZ` / `JNZ` / `BR_*`） | 虚拟机实现简单；前端生成结构化循环，但把它们降级成跳转。结构化的 `LOOP` 操作码可能在后续版本中加入，需要做一次版本号提升。 |
| 值模型 | **64 位槽位** | reader 的值都是大小、计数、tag 和索引，均小于 `2^63`。`uint64` 标识符原样传递。 |
| 整数语义 | 64 位二进制补码，环绕（wrapping） | 与 C++ 虚拟机一致；与 Python 的任意精度语义存在已记录的差异。 |
| 布尔结果 | `0` / `1` | 比较和 `bool(...)` 产生 `0`/`1`；布尔缓冲区存 `uint8` 值。 |
| 浮点 | **只做搬运** | reader 只需要把 `float32`/`float64` 从流里拷到缓冲区；不需要浮点运算。浮点算术操作码已预留但未实现。 |
| `READ_FIELDS` 布局 | **仅支持扁平布局** | 一个布局是标量 / 跳过 / 定长数组字段组成的序列。嵌套 reader 用 `CALL` 加细粒度操作码表达。 |
| 字符串 | **驻留（interned）id** | 字符串存放在 run 局部的 arena 中；寄存器携带其 `u32` id，永不携带字节本身。`-1` 表示“没有字符串”。 |
| 缓冲区检查 | **始终开启** | 每次流访问都做边界检查；越界时抛 Python 异常，而不是让进程崩溃。 |

```{note}
字符串是某个 arena 中的 id，该 arena 依次预置了模块的常量，因此
`STR_CONST rd, k` 取的就是下标为 `k` 的常量。`SREAD_CSTR` 会把读到的东西驻留，
于是 `STR_EQ` 退化为 id 比较，`AnyPointerReader` 用两条指令就能比较类名。
```

---

## 2. 架构

```{mermaid}
flowchart LR
    reader["Python Reader 类"] --> front["前端（AST 分析）"]
    front --> module["模块（字节码 + 表）"]
    module --> cache[("磁盘缓存<br/>内容哈希")]
    module --> vm["VM（先 Python，后 C++）"]
    vm --> buffers["带类型的缓冲区"]
    buffers --> ak["awkward 数组（Python）"]
```

**模块**是缓存和分发的单位。它包含虚拟机所需的一切：代码、缓冲区声明、状态声明、
字符串常量、类型布局和函数表。模块可以序列化到磁盘，并以内容哈希作为键，因此结构
相同的 reader 树会共享同一个已编译模块。

---

## 3. 模块格式

```text
magic        "UCIR"
isa_major    u16            # 不兼容变更
isa_minor    u16            # 向后兼容的新增
entry        u16            # 每个 event 执行一次的函数 id
regs_max     u16            # 用于验证的寄存器上界

buffers[]    { name, dtype:u8, kind:u8, init:i64 }
states[]     { name, init:i64 }
strings[]    [ ... ]        # 类名与消息模板
layouts[]    { id, fields: [ { kind, typecode, count, buffer_id } ] }
funcs[]      { id, name, arity:u8, reg_count:u16, code_off:u32, code_len:u32 }
code[]       Ins[]          # 可执行形式中每条 12 字节
lines[]      ip -> 源码行（可选，用于报错与跟踪）
```

- 缓冲区的 **`kind`** 取值为 `DATA`（元素存储）、`OFFSETS`（int64 偏移，初始化为
  一个 `0`）或 `COUNT`（int64 计数器）。
- **`arity`** 对于 `read()` 是 `0`，对于 `read_many(count)`、
  `read_until(end_pos)` 和 `read_many_memberwise(count)` 是 `1`。
- **`layouts`** 是扁平的。`field.kind` 取 `SCALAR`、`SKIP`、`ARRAY_FIXED`、
  `TOBJECT_SKIP` 之一。
- **每个分支一个模块**意味着该分支的所有 reader 实例共享同一个 id 空间：缓冲区 id、
  状态槽位和函数 id 都是模块全局的。

### 确定性标识符

id 由对 reader 树的一次确定性遍历分配（根在前，然后按声明顺序遍历子节点）。它们
**不得**由 `hash(obj)` 或分支名派生，这样两个结构相同的分支会产出逐字节相同的模块，
从而可以按内容哈希去重。

---

## 4. 运行时模型

```text
VM
├── regs[0..R)        64 位槽位，每个调用帧一个窗口
├── frames            (func_id, return ip, return register)
├── stream            data[], entry_offsets[], cursor, initial_cursor, event_end
├── buffers[]         { dtype, kind, storage, count }
├── states[]          每个 reader 实例的 64 位标量状态
├── refs              map<u32, Ref{kind, object_index, class_name}>
└── strings           常量池与运行时字符串 arena
```

### 值

一个寄存器持有 64 位槽位。整数操作码把它解释为有符号或无符号；浮点值以其
IEEE-754 位模式存储，只被搬运，从不参与计算。前端在静态阶段知道每个表达式的类型，
但虚拟机无需跟踪类型。

### 缓冲区

缓冲区在一次 run 期间只追加。`OFFSETS` 缓冲区以一个 `0` 元素起始，这使得
`BUF_APPEND_OFFSET` 成为单条指令的更新。`HALT` 之后，每个缓冲区以声明的 dtype
暴露给 Python，成为一个 NumPy 数组。

### Reader 状态

`STATE_*` 操作码访问 reader 实例上需要跨 event 持久化的标量字段（例如
`AnyPointerReader` 中的 `object_counter`）。配置值（`with_header`、`flat_size`、
`dtype`）是**常量**，会被前端折叠进代码或操作数中。

---

## 5. 指令编码

可执行形式采用定长编码，以求简单：

```cpp
struct Ins {
    uint8_t op;      // 操作码
    uint8_t rd;      // 目标寄存器
    uint8_t ra;      // 源寄存器 A
    uint8_t rb;      // 源寄存器 B
    int32_t imm1;    // 立即数 / BUF / SLOT / FUNC / LAYOUT / MSG / TC
    int32_t imm2;    // 跳转目标 / 第二个立即数 / 步长（stride）
};
```

下文使用的操作数记号：

| 符号 | 含义 |
|---|---|
| `rd`, `ra`, `rb` | 寄存器编号（0–255） |
| `IMM` | 立即数 |
| `BUF` | 缓冲区 id |
| `TC` | typecode |
| `SLOT` | 状态槽位 id |
| `FUNC` | 函数 id |
| `LBL` | 绝对指令下标 |
| `LAYOUT` | 布局 id |
| `MSG` | 消息 id（`strings` 的下标） |
| `CONST` | 字符串常量 id |

计划为磁盘存储增加紧凑的 varint 编码；语义不变。

---

## 6. 指令集

### 6.1 控制与常量

| 操作码 | 十六进制 | 操作数 | 语义 |
|---|---|---|---|
| `HALT` | 0x00 | — | 停止执行；虚拟机返回缓冲区。 |
| `NOP` | 0x01 | — | 空操作。 |
| `LINE` | 0x02 | `IMM` | 记录源码行（仅调试）。 |
| `DEBUG_PRINT` | 0x03 | `MSG`, `ra` | 打印调试消息（默认关闭）。 |
| `CONST` | 0x10 | `rd`, `IMM` | `rd = IMM`（64 位）。 |
| `CONST_F` | 0x11 | `rd`, `IMM` | `rd = double 的位模式`（为搬运预留）。 |
| `MOV` | 0x12 | `rd`, `ra` | `rd = ra`。 |
| `ZEXT32`/`ZEXT16`/`ZEXT8` | 0x13/0x15/0x17 | `rd`, `ra` | 零扩展低 32/16/8 位。 |
| `SEXT32`/`SEXT16`/`SEXT8` | 0x14/0x16/0x18 | `rd`, `ra` | 符号扩展低 32/16/8 位。 |

### 6.2 整数算术

所有运算按模 `2^64` 环绕；除法和取模向零截断，与 C++ 一致。

| 操作码 | 十六进制 | 操作数 | 语义 |
|---|---|---|---|
| `ADD` | 0x20 | `rd`, `ra`, `rb` | `rd = ra + rb` |
| `SUB` | 0x21 | `rd`, `ra`, `rb` | `rd = ra - rb` |
| `MUL` | 0x22 | `rd`, `ra`, `rb` | `rd = ra * rb` |
| `DIV_S` | 0x23 | `rd`, `ra`, `rb` | 有符号除法 |
| `DIV_U` | 0x24 | `rd`, `ra`, `rb` | 无符号除法 |
| `MOD_S` | 0x25 | `rd`, `ra`, `rb` | 有符号取余 |
| `MOD_U` | 0x26 | `rd`, `ra`, `rb` | 无符号取余 |
| `NEG` | 0x27 | `rd`, `ra` | `rd = -ra` |
| `SHL` | 0x28 | `rd`, `ra`, `rb` | 左移 |
| `SHR_S` | 0x29 | `rd`, `ra`, `rb` | 算术右移 |
| `SHR_U` | 0x2A | `rd`, `ra`, `rb` | 逻辑右移 |
| `AND` | 0x2B | `rd`, `ra`, `rb` | 按位与 |
| `OR` | 0x2C | `rd`, `ra`, `rb` | 按位或 |
| `XOR` | 0x2D | `rd`, `ra`, `rb` | 按位异或 |
| `NOT` | 0x2E | `rd`, `ra` | 按位取反 |
| `NOT_B` | 0x2F | `rd`, `ra` | 逻辑非，结果为 `0`/`1` |

```{note}
操作码 `0x30`–`0x3F` 预留给浮点算术
（`FADD`、`FSUB`、`FMUL`、`FDIV`、`FNEG`、`I2F`、`F2I`）。它们在 **v0 中未实现**：
reader 只在流与缓冲区之间搬运浮点值。
```

### 6.3 比较

结果恒为 `0` 或 `1`。

| 操作码 | 十六进制 | 操作数 | 语义 |
|---|---|---|---|
| `CMP_EQ` | 0x40 | `rd`, `ra`, `rb` | `ra == rb` |
| `CMP_NE` | 0x41 | `rd`, `ra`, `rb` | `ra != rb` |
| `CMP_LT_S` | 0x42 | `rd`, `ra`, `rb` | 有符号 `ra < rb` |
| `CMP_LE_S` | 0x43 | `rd`, `ra`, `rb` | 有符号 `ra <= rb` |
| `CMP_GT_S` | 0x44 | `rd`, `ra`, `rb` | 有符号 `ra > rb` |
| `CMP_GE_S` | 0x45 | `rd`, `ra`, `rb` | 有符号 `ra >= rb` |
| `CMP_LT_U` | 0x46 | `rd`, `ra`, `rb` | 无符号 `ra < rb` |
| `CMP_LE_U` | 0x47 | `rd`, `ra`, `rb` | 无符号 `ra <= rb` |
| `CMP_GT_U` | 0x48 | `rd`, `ra`, `rb` | 无符号 `ra > rb` |
| `CMP_GE_U` | 0x49 | `rd`, `ra`, `rb` | 无符号 `ra >= rb` |

### 6.4 控制流

| 操作码 | 十六进制 | 操作数 | 语义 |
|---|---|---|---|
| `JMP` | 0x50 | `LBL` | 无条件跳转。 |
| `JZ` | 0x51 | `ra`, `LBL` | 若 `ra == 0` 则跳转。 |
| `JNZ` | 0x52 | `ra`, `LBL` | 若 `ra != 0` 则跳转。 |
| `BR_EQ` | 0x53 | `ra`, `rb`, `LBL` | 若 `ra == rb` 则跳转。 |
| `BR_NE` | 0x54 | `ra`, `rb`, `LBL` | 若 `ra != rb` 则跳转。 |
| `BR_LT_S` | 0x55 | `ra`, `rb`, `LBL` | 有符号小于分支。 |
| `BR_LE_S` | 0x56 | `ra`, `rb`, `LBL` | 有符号小于等于分支。 |
| `BR_GT_S` | 0x57 | `ra`, `rb`, `LBL` | 有符号大于分支。 |
| `BR_GE_S` | 0x58 | `ra`, `rb`, `LBL` | 有符号大于等于分支。 |
| `BR_LT_U`/`BR_LE_U`/`BR_GT_U`/`BR_GE_U` | 0x59–0x5C | `ra`, `rb`, `LBL` | 无符号变体。 |
| `CALL` | 0x5D | `rd`, `FUNC`, `ra` | 以参数 `ra` 调用 `FUNC`；结果放入 `rd`。 |
| `RET` | 0x5E | `ra` | 把 `ra` 返回给调用者。 |

融合的 `BR_*` 操作码属于性能档：`CMP_*` 后接 `JZ`/`JNZ` 等价，但多一次分派开销。

### 6.5 流访问

每次访问都会对当前 event 的数据做边界检查。越界会抛
`StreamUnderflow` / `ReadLengthMismatch`。

| 操作码 | 十六进制 | 操作数 | 语义 |
|---|---|---|---|
| `SREAD` | 0x60 | `rd`, `TC` | 读一个类型为 `TC` 的大端标量。 |
| `SREAD_FNB` | 0x61 | `rd` | 读 `fNBytes`，校验字节计数掩码，返回掩码后的值。 |
| `SREAD_VERSION` | 0x62 | `rd` | 读 int16 的 `fVersion`。 |
| `SREAD_CSTR` | 0x63 | `rd` | 读一个 NUL 结尾的字符串并驻留；`rd` 得到其 arena id。 |
| `SREAD_TSTRING` | 0x64 | `rd`, `BUF` | 把一个 `TString` 读入字节缓冲区（预留）。 |
| `SKIP` | 0x65 | `IMM` | 游标前进一个常量。 |
| `SKIP_R` | 0x66 | `ra` | 游标前进一个寄存器中的值。 |
| `SKIP_FNB` | 0x67 | — | 跳过 `fNBytes`（仍校验掩码）。 |
| `SKIP_VERSION` | 0x68 | — | 跳过 2 字节。 |
| `SKIP_TOBJECT` | 0x69 | — | 跳过一个 `TObject` 头部。 |
| `SKIP_OBJHDR` | 0x6A | — | 跳过 `fNBytes` + tag（若为新类，还跳过类名）。 |
| `SKIP_CSTR` | 0x6B | — | 跳过一个 NUL 结尾的字符串。 |
| `CURSOR` | 0x6C | `rd` | `rd = cursor`。 |
| `SET_CURSOR` | 0x6D | `ra` | `cursor = ra`（带边界检查）。 |
| `ENTRIES` | 0x6E | `rd` | basket 中的 event 数量。 |
| `INIT_OFFSET` | 0x6F | `rd` | 流的 `initial_cursor_position`。 |
| `DATA_SIZE` | 0x70 | `rd` | 当前 event 数据的长度。 |

### 6.6 Event 偏移

| 操作码 | 十六进制 | 操作数 | 语义 |
|---|---|---|---|
| `OFFSET_AT` | 0x71 | `rd`, `ra` | `rd = entry_offsets[ra]`。 |
| `OFFSET_SEEK` | 0x72 | `rd`, `ra` | 严格大于 `ra` 的最小 entry 偏移。 |
| `EVENT_END` | 0x73 | `rd` | `rd = entry_offsets[event + 1]`。 |

`OFFSET_SEEK` 取代了现有 reader 代码中唯一的 NumPy 操作
（`CStyleArrayReader` 搜索锯齿数组的末尾）。

### 6.7 粗粒度读取

这些是性能档。dense 变体必须在虚拟机内部跑原生循环，而不是逐元素分派。

| 操作码 | 十六进制 | 操作数 | 语义 |
|---|---|---|---|
| `READ_BULK` | 0x78 | `BUF`, `TC`, `ra` | 连续读 `ra` 个元素到 `BUF`。 |
| `READ_STRIDED` | 0x79 | `BUF`, `TC`, `ra`, `rb` | 读 `ra` 个元素（间隔 `rb` 字节）到 `BUF`。 |
| `READ_FIELDS` | 0x7A | `LAYOUT`, `ra` | 读 `ra` 个某布局的扁平对象到各自的缓冲区。 |
| `READ_APPEND` | 0x7B | `BUF`, `TC` | 读一个元素并追加（`SREAD` + `BUF_APPEND` 的融合）。 |

### 6.8 缓冲区访问

| 操作码 | 十六进制 | 操作数 | 语义 |
|---|---|---|---|
| `BUF_APPEND` | 0x80 | `BUF`, `ra` | `BUF.append(ra)`。 |
| `BUF_APPEND_CONST` | 0x81 | `BUF`, `IMM` | 追加一个常量。 |
| `BUF_APPEND_OFFSET` | 0x82 | `BUF`, `ra` | `BUF.append(BUF[-1] + ra)`。 |
| `BUF_APPEND_LEN` | 0x83 | `BUF`, `BUF` | `dst.append(len(src))`。 |
| `BUF_LAST` | 0x84 | `rd`, `BUF` | `rd = BUF[-1]`。 |
| `BUF_LEN` | 0x85 | `rd`, `BUF` | `rd = len(BUF)`。 |
| `BUF_RESERVE` | 0x86 | `BUF`, `ra` | 预留容量（提示，可以是空操作）。 |

### 6.9 Reader 状态

| 操作码 | 十六进制 | 操作数 | 语义 |
|---|---|---|---|
| `STATE_GET` | 0x88 | `rd`, `SLOT` | `rd = states[SLOT]`。 |
| `STATE_SET` | 0x89 | `SLOT`, `ra` | `states[SLOT] = ra`。 |
| `STATE_IADD` | 0x8A | `SLOT`, `IMM` | `states[SLOT] += IMM`。 |

### 6.10 对象引用

供 `AnyPointerReader` 使用。Python 中存放 `_Reference` 对象的 `dict` 被这些操作码
取代，这样 DSL 永远看不到容器类型。

| 操作码 | 十六进制 | 操作数 | 语义 |
|---|---|---|---|
| `REF_HAS` | 0x90 | `rd`, `ra` | `rd = (tag in refs)`。 |
| `REF_GET_OBJ` | 0x91 | `rd`, `ra` | 引用的对象索引。 |
| `REF_GET_CLASS` | 0x92 | `rd`, `ra` | 引用的类名 id；没有时为 `-1`。 |
| `REF_SET_OBJ` | 0x93 | `ra`, `rb` | 存一个对象引用。 |
| `REF_SET_CLASS` | 0x94 | `ra`, `rb` | 存一个类引用。 |
| `REF_COUNT` | 0x95 | `rd` | 条目数量。 |

### 6.11 字符串

已分配操作码，但**在 v0 中未实现**；执行其中任何一条都会抛
`UnsupportedFeature`。

| 操作码 | 十六进制 | 操作数 | 语义 |
|---|---|---|---|
| `STR_CONST` | 0x98 | `rd`, `CONST` | 载入驻留的常量字符串。 |
| `STR_EQ` | 0x99 | `rd`, `ra`, `rb` | 字符串相等，结果为 `0`/`1`。 |
| `STR_STORE` | 0x9A | `SLOT`, `ra` | 把字符串存入 reader 状态。 |
| `STR_LOAD` | 0x9B | `rd`, `SLOT` | 从 reader 状态载入字符串。 |

### 6.12 校验与错误

| 操作码 | 十六进制 | 操作数 | 语义 |
|---|---|---|---|
| `ASSERT` | 0xA0 | `ra`, `MSG` | 除非 `ra != 0`，否则失败。 |
| `ASSERT_CURSOR_EQ` | 0xA1 | `ra`, `MSG` | 除非 `cursor == ra`，否则失败。 |
| `ASSERT_STR_EQ` | 0xA2 | `ra`, `rb`, `MSG` | 除非字符串相等，否则失败。 |
| `THROW` | 0xA3 | `MSG` | 抛出一个无条件的 reader 错误。 |

---

## 7. 调用约定

- 每个 reader 实例最多暴露四个函数：`read()`（arity 0）、`read_many(count)`、
  `read_until(end_pos)` 和 `read_many_memberwise(count)`（arity 1）。
- `CALL rd, FUNC, ra` 把 `ra` 作为参数传入，并把返回值存入 `rd`。被调函数有独立的
  寄存器窗口；`RET ra` 返回 `ra`。
- 当 reader 未覆写默认实现时，前端可以为其生成默认实现：`read_many` 和
  `read_until` 都是围绕 `read` 的循环。
- 静态可知的叶子 reader 应由前端内联。`CALL` 只用于递归结构、指针图和
  member-wise 分派。
- reader 上的辅助方法（例如 `read_body`）变成 arity 为 0 或 1 的普通函数。在 JIT
  路径上，方法不得返回元组。

---

## 8. Event 循环

虚拟机拥有按 basket 的循环；字节码永远看不到它：

```text
cursor = 0
for event in range(entries):
    event_end = entry_offsets[event + 1]
    call entry_function
    if cursor != event_end: raise ReadLengthMismatch
```

这样 Python/C++ 边界保持在每个 basket 一次调用，且每个 event 可以独立校验。

---

## 9. 与 Python reader API 的映射

| Python | 操作码 |
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
| `self.with_header`（常量） | 常量操作数 / 折叠后的分支 |
| `if cond:` | `JZ cond, else` |
| `for _ in range(n): body` | `CONST i,0; L: BR_GE_S i,n,end; body; ADD i,i,1; JMP L` |
| `while stream.cursor < end:` | `L: CURSOR r; BR_GE_S r,end,end; body; JMP L` |
| `self.read(stream)` | `CALL rd, FUNC_read` |
| `self.child.read_many(stream, n)` | `CALL rd, FUNC_read_many, n` |
| `assert stream.cursor == end_pos` | `ASSERT_CURSOR_EQ end, MSG` |
| `raise NotImplementedError` | `THROW MSG` |

`min`、`max`、`len`、`bool`、`int` 以及整数/按位运算符由算术和比较操作码覆盖。
NumPy 与 `dict` 操作**不**属于 ISA 的一部分。

---

## 10. 完整示例

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

不做融合时：

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

使用计数循环融合后：

```text
  SREAD              r0, I
  BUF_APPEND_OFFSET  offsets, r0
  READ_BULK          data, TC, r0
  RET
```

### 10.3 `TObjectReader`（`keep_data = True`）

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

元素 reader 通过 `CALL` 调用，计数放在 `r4` 对应的参数寄存器中。如果元素是原始类型
reader，前端可以内联它并直接发射 `READ_BULK`。

### 10.5 `CStyleArrayReader`（锯齿分支）

```text
  CURSOR         r0
  OFFSET_SEEK    r1, r0
  CALL           r2, func[element.read_until], r1
  BUF_APPEND_OFFSET offsets, r2
  RET
```

---

## 11. 校验与错误

虚拟机在执行前校验模块：

- 每个寄存器下标都小于所属函数的 `reg_count`；
- 每个跳转目标都落在所属函数内部；
- 每个被引用的 `BUF`、`SLOT`、`FUNC`、`LAYOUT`、`CONST` 和 `MSG` 都存在；
- 每个 typecode 都是已知的；
- `entry` 指向一个存在的函数；
- `isa_major` 与虚拟机匹配。

运行时错误携带指令下标、源码行（可用时）、游标位置和字节偏移。错误类型如下：

| 错误 | 触发条件 |
|---|---|
| `StreamUnderflow` | 一次读或跳过会越过该 event 的数据边界。 |
| `InvalidByteCount` | `fNBytes` 缺少 `kByteCountMask`。 |
| `ReadLengthMismatch` | `read` 结束后游标不在 event 边界上。 |
| `UnsupportedFeature` | 执行了预留操作码（浮点算术、`SREAD_TSTRING`）。 |
| `AssertionFailed` | 某个 `ASSERT*` 操作码失败。 |
| `StackOverflow` | 超过调用深度上限。 |

---

## 12. 性能指引

虚拟机的开销主要由分派频率决定，因此前端必须把热循环保持在粗粒度操作码里：

| 模式 | 必需的操作码 | 目标 |
|---|---|---|
| 标量数组、`vector<primitive>` | `READ_BULK` | ≤ 1.5 ns/元素 |
| 扁平结构体数组 | `READ_FIELDS` | ≤ 2 ns/元素 |
| 偏移记录 | `BUF_APPEND_OFFSET` | 每元素一条指令 |
| 单元素热路径 | `READ_APPEND` | ≤ 2 ns/元素 |
| 循环控制 | 融合的 `BR_*` | 每次迭代一次分派 |
| 缓冲区增长 | `BUF_RESERVE` | 避免几何式重新分配 |

如果某个 reader 每元素执行三条及以上操作码，它会比当前的 C++ reader 图慢好几倍。
前端存在融合（fusion）这一趟，正是为了在
[Reader JIT 重构计划](reader-jit-refactor.zh-cn.md)中列出的典型模式上避免这种情况。

---

## 13. v0 范围

**v0 已实现**

- 寄存器机、64 位整数语义、返回 `0`/`1` 的比较；
- `READ_BULK`、`READ_STRIDED`、`READ_FIELDS`、`READ_APPEND`；
- 缓冲区（`DATA`、`OFFSETS`、`COUNT`）、reader 状态、`OFFSET_SEEK`；
- 字符串 arena 以及 `STR_*` / `ASSERT_STR_EQ` / `SREAD_CSTR` 操作码，以及完整的
  `REF_*` 集合——这正是 `AnyPointerReader` 所需要的；
- 扁平控制流与融合分支；
- 每个分支一个模块、内容哈希缓存、确定性 id；
- 全部 12 个内置 reader。

**延后**

- 浮点算术操作码（reader 只搬运浮点值）；
- `SREAD_TSTRING`（reader 改用 `SREAD`/`READ_BULK` 逐字节走）；
- 结构化的 `LOOP` 操作码（目前只有扁平跳转）；
- 紧凑的序列化格式；
- C++ 虚拟机（Python 虚拟机先作为参考实现）。

---

## 14. 待定问题

1. **`READ_FIELDS` 快速路径的范围。** 目前只支持扁平布局；含嵌套容器或自定义子
   reader 的类走 `CALL`。
2. **模块去重。** 每个分支一个模块时，相同的分支按内容哈希去重。这要求 id 和代码
   生成具有严格的确定性。
3. **寄存器分配。** 前端可以使用简单的线性扫描分配器；虚拟机只需要每个函数的
   `reg_count`。
4. **缓存位置与失效。** 建议的键：生成模块字节的哈希，并以
   `isa_major`/`isa_minor` 和包版本做版本化。
5. **调试。** 计划提供带指令级跟踪的 Python 参考虚拟机；C++ 虚拟机将以其为基准做
   验证。
