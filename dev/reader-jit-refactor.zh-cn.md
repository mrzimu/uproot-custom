# Reader JIT 重构计划

> 本文是 [`reader-jit-refactor.md`](reader-jit-refactor.md) 的中文译本，内容与原文
> 一一对应；如有歧义，以英文原文为准。

```{important}
**状态：部分实现。** 阶段 0（模块格式、验证器、Python 虚拟机、builder）以及面向
内置构造的前端已在 `uproot_custom/readers/jit/` 中实现，并可通过
`backend.use("jit")` 选用。

当前实现与下面的计划有一处不同：它没有去翻译现有的 `Reader` 类（条目 R1–R9），
而是让 JIT 栈拥有自己的 `Node` 类——把 factory 与 reader 合并在一起，结构声明、
字节码生成和 awkward 重建都在同一个对象里——以及自己的 `build_node`，把 streamer
信息转换成这棵树。现有的 `Reader` 和 `Factory` 类未被改动，并在差分测试中充当
oracle。

仍未完成的部分：面向*用户自写* reader 的 AST 前端（R1–R9 与 `declare_*`）、
C++ 虚拟机以及磁盘上的模块缓存。`AnyPointerReader` 已被覆盖——字符串与引用操作码
均已实现——因此全部十二个内置 reader 都能编译。如果某分支的树中包含前端没有对应
节点的东西，该分支仍会回落到 Python reader 树。
```

## 1. 目标

如今，想要一个快速的定制 reader，用户必须把逻辑写两遍：一遍用 Python（用于开发），
一遍用 C++（用于生产），然后再构建一个 pybind11 扩展。C++ 这一步是分发障碍：下游
包需要 C++17 工具链和 CMake，而且任何改动都需要重新构建。

JIT 计划去掉了这一步：

```text
用户只写一个 Python Reader
        │
        ├── Python 后端（参考解释器，始终可用）
        └── JIT 前端 → 字节码 → 虚拟机（快，无需 C++ 工具链）
```

Python 后端仍然是事实来源与兜底方案。JIT 是一个按分支选用、可选的加速器。

## 2. 为什么 reader 需要改造

现有 reader 是普通的 Python 对象。大部分读取逻辑可以干净地映射到 ISA，但少数模式
难以翻译甚至无法翻译：

| 现有模式 | 问题 |
|---|---|
| `self._data = array("B")` | 缓冲区的 dtype 和 kind 是隐含的；前端得去检查 `array` 的 typecode |
| `self.buffer_reader = DTYPE_TO_READER[dtype]` 然后 `self.buffer_reader(stream)` | 存了一个绑定方法；调用目标无法被静态解析 |
| `stream.refs[tag].object_index`、`_Reference(...)` | Python `dict` + dataclass + union；ISA 中没有对应物 |
| `(entry_offsets > cursor).nonzero()[0].min()` | 读取路径里出现了 NumPy 操作 |
| `assert ... f"...{self.name}..."` | f-string 消息无法在编译期求值 |
| 用 `hash(self)` 生成 reader id | 跨进程不确定，破坏了内容哈希缓存 |
| 子 reader 通过任意属性被发现 | 遍历顺序没有保证 |

因此改造是**声明式为主**的：把已有信息显式化，并用命名原语替换少数无法映射的表达式。
读取逻辑本身保持不变。

## 3. 原则

1. **显式声明。** 缓冲区、标量状态、编译期常量和子 reader 都通过基类声明，而不是
   从任意 Python 代码里推断。
2. **可映射的原语。** 读取路径只使用与操作码一一对应的操作。NumPy、`dict`、
   dataclass 和动态消息都退到命名方法之后。
3. **确定性标识符。** id 来自确定性遍历，绝不来自 `hash(obj)` 或分支名，这样结构
   相同的分支会产出相同的模块。
4. **`data()` 保持不变。** 它仍然用 `np.asarray(buf)` 构建数组；Python 后端提供
   `array.array` 缓冲区，虚拟机提供 NumPy 数组，两种情况 `np.asarray` 都接受。
5. **优雅回退。** 如果某个 reader 不遵守规则，前端报告一次，该分支改用 Python 后端。
   绝不以牺牲正确性换取速度。

## 4. 重构条目

每个条目给出当前代码与改造后的代码。

### R1. 声明缓冲区、状态、常量和子 reader

```python
# 改造前
self.with_header = with_header
self.element_reader = element_reader
self.offsets = array("q", [0])
self._data = array("B")
```

```python
# 改造后
self.with_header    = self.declare_const("with_header", with_header)
self.element_reader = self.declare_reader("element", element_reader)
self.offsets        = self.declare_buffer("offsets", "int64", kind=OFFSETS)
self._data          = self.declare_buffer("data", "uint8")
```

前端直接读取这些声明；无需对 `array` 调用做类型推断。`declare_const` 区分的正是
那些可以折叠的值，与可变的 `declare_state` 槽位相对。

### R2. 通过显式原语读取标量

```python
# 改造前 —— 通过存储的绑定方法做间接调用
self.buffer_reader = DTYPE_TO_READER[dtype]
self._data.append(self.buffer_reader(stream))
```

```python
# 改造后
self.dtype = self.declare_const("dtype", dtype)
self._data.append(stream.read_scalar(self.dtype))
```

`stream.read_scalar(TC)` 映射到 `SREAD rd, TC`。由于 `dtype` 是声明过的常量，
typecode 在编译期即为已知。

### R3. 用命名方法替换 `refs` 字典

```python
# 改造前
idx = stream.refs[fTag].object_index
if fTag not in stream.refs: ...
stream.refs[key] = _Reference(type="object", object_index=n)
len(stream.refs)
```

```python
# 改造后
idx = stream.refs.get_object(fTag)
if not stream.refs.has(fTag): ...
stream.refs.set_object(key, n)
stream.refs.count()
```

映射到 `REF_*` 操作码。DSL 从此看不到容器类型或 union。

### R4. 用命名原语替换 NumPy 偏移搜索

```python
# 改造前
end_offset_index = (entry_offsets > cursor_pos).nonzero()[0].min()
end_pos = entry_offsets[end_offset_index]
```

```python
# 改造后
end_pos = stream.next_offset_after(stream.cursor)
```

映射到单条 `OFFSET_SEEK`。这是读取路径里唯一的 NumPy 操作。

### R5. 用命名检查替换 f-string 断言

```python
# 改造前
assert stream.cursor == end_pos, (
    f"{self.__class__.__name__}({self.name}): Invalid read length! "
    f"Expect {fNBytes} bytes, but read {stream.cursor - start_pos} bytes."
)
```

```python
# 改造后
stream.expect_end(end_pos, "AnyClass")
```

映射到 `ASSERT_CURSOR_EQ end_pos, MSG`。消息由一个常量 id 加一个源码行组成，由虚拟机
解析。

### R6. 让字符串比较走方法（前端工作）

```python
# 改造后
name = stream.read_cstr()                  # SREAD_CSTR -> arena id
self.check_class_name(name)                # STR_EQ + ASSERT_STR_EQ
```

字符串与引用操作码已经存在（[ISA](isa.zh-cn.md) 第 6.10 与 6.11 节），
`AnyPointerReader` 就是由它们编译出来的。仍然缺少的是这个条目本身：能识别用户
reader 中这种写法的 AST 前端。目前由手写节点完成这件事，见
`nodes/anypointer.py`。

### R7. 子 reader 列表必须声明且不可变

```python
# 改造后
self.element_readers = self.declare_readers("elements", [r0, r1, r2])
...
for reader in self.element_readers:        # 在编译期展开
    reader.read(stream)
```

只支持 `for reader in self.<已声明的_reader_列表>` 这一形式；该列表是个元组，会被
展开成每个元素一次 `CALL`。运行时变化的列表无法翻译。

### R8. 读取辅助方法不得返回元组或多值

```python
# 改造前
def read_element_version(self, stream):
    version = stream.read_fVersion()
    checksum = None
    if version == 0:
        checksum = stream.read_uint32()
    return version, checksum      # 调用方会忽略它
```

```python
# 改造后
def read_element_version(self, stream) -> None:
    if stream.read_fVersion() == 0:
        stream.skip(4)
```

`CALL` 只有一个返回值。arity 为 0 或 1 的辅助方法是允许的；元组不行。

### R9. 确定性 id 与遍历

```python
# 改造前（readers/_forth.py）
obj_hash = str(hash(self))
for i in range(10):
    obj_hash = obj_hash.replace(str(i), chr(ord("a") + i))
```

```python
# 改造后
# id 按遍历顺序分配：root = 0，然后按声明顺序遍历子节点；
# 或者由稳定路径派生，例如 "root.element"
def children(self) -> tuple[IReader, ...]: ...
```

确定性 id 正是“每分支一个模块”缓存能成立的前提：两个结构相同的分支必须产出逐字节
相同的模块，然后按内容哈希去重。

## 5. 基类 API

```python
class IReader:
    # 声明，在 __init__ 中调用
    def declare_buffer(self, name, dtype, kind=DATA) -> Buffer
    def declare_state(self, name, init=0) -> int
    def declare_const(self, name, value) -> Const
    def declare_reader(self, name, reader) -> IReader
    def declare_readers(self, name, readers) -> tuple[IReader, ...]
    def children(self) -> tuple[IReader, ...]

    # 默认方法；前端可以改为生成这些函数体
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

    # 不变；在两个后端上都以 Python 运行
    def data(self): ...
```

```python
class BinaryStream:
    # 标量读取 -> SREAD
    def read_scalar(self, dtype)
    def read_fNBytes(self); def read_fVersion(self)
    # 跳过 -> SKIP*
    def skip(self, n); def skip_fNBytes(self); def skip_fVersion(self)
    def skip_TObject(self)
    # 流状态 -> CURSOR / SET_CURSOR / ENTRIES / INIT_OFFSET
    cursor: int
    entries: int
    initial_cursor_position: int
    def next_offset_after(self, pos) -> int
    refs: Refs
    # 显式粗粒度辅助方法（可选，直接映射到 READ_*）
    def read_bulk(self, buf, dtype, count)
    def read_strided(self, buf, dtype, stride, count)
```

把 `declare_*` 的默认实现保持为空操作并返回原对象，这样按旧 API 编写的第三方 reader
在 Python 后端上仍能运行。

## 6. 典型模式与融合规则

前端的融合这一趟会识别下列形式并用粗粒度操作码替换。这也正是编写新 reader 的推荐
写法。

| 典型 Python | 发射的操作码 |
|---|---|
| `for _ in range(n): buf.append(stream.read_scalar(tc))` | `READ_BULK buf, tc, n` |
| `buf.append(stream.read_scalar(tc))` | `READ_APPEND buf, tc` |
| `buf.append(buf[-1] + x)` | `BUF_APPEND_OFFSET buf, x` |
| `for _ in range(n): <扁平字段序列>` | `READ_FIELDS layout, n` |
| `buf.append(len(src))` | `BUF_APPEND_LEN buf, src` |
| `if (cmp): ...` | `BR_*` 融合的比较并分支 |

```{note}
融合只适用于完全符合典型形式的情形。用户 reader 如果写了不寻常的循环，仍然能编译，
但会回落到细粒度操作码，速度相应更慢。当热循环未被融合时，前端应当给出警告。
```

## 7. 不支持的模式

前端会报告下列情况，并让该分支回落到 Python 后端：

- 存储并调用绑定方法（`self.buffer_reader`）；
- `getattr` / `setattr`、`**kwargs`、装饰器；
- 读取路径中的 `try` / `except`、推导式、lambda、生成器；
- 读取路径中的 NumPy、`dict`、`set` 或 `isinstance`；
- f-string 断言或动态构造的消息；
- 在运行时遍历 reader 的列表或字典（只支持已声明且不可变的 reader 列表）；
- 未声明就读 `self.<attr>`；
- 非确定性 id。

## 8. 推进路线

### 阶段 0 —— 先做 Python 虚拟机

**在写任何 C++ 之前，先用 Python 把虚拟机建起来。** Python 虚拟机是参考实现。
它比最终的 C++ 虚拟机慢，但是：

- 没有构建步骤，因此 ISA 和前端可以快速迭代；
- 可以跟踪每条指令，让 ISA 缺陷与前端缺陷一目了然；
- 可作为对照 Python 后端做差分测试的 oracle；
- 在模块格式和缓存方案被冻结之前，先证明它们是可行的。

阶段 0 交付物：

1. 模块数据结构与验证器；
2. 实现 v0 操作码集合的 Python 虚拟机；
3. 一个用于手工构造模块的 builder API；
4. 针对算术、控制流、缓冲区、偏移和粗粒度读取的单元测试。

本阶段明确不以性能为目标。

### 阶段 1 —— 改造 reader 并添加前端

- 在 `readers/python.py` 上实现 R1–R9，并保持 Python 后端全部通过；
- 实现 AST 前端与融合这一趟；
- 加入按分支的模块生成、确定性 id 和内容哈希缓存；
- 差分测试：`python` 后端对比 Python 虚拟机，逐元素比较。

### 阶段 2 —— 把虚拟机迁移到 C++

只有在 ISA、前端和测试套件都稳定之后：

- 用相同的字节码和相同的模块格式把虚拟机移植到 C++；
- 在每个 fixture 上让 C++ 虚拟机对跑 Python 虚拟机（Python 虚拟机是 oracle）；
- 与当前的 C++ reader 图做基准对比，并落实 [ISA](isa.zh-cn.md) 中的目标。

由于字节码与后端无关，这次迁移是机械性的。reader 代码不需要改动。

### 阶段 3 —— 延后的特性

- 浮点算术，仅在某个 reader 确实需要时才做；
- `SREAD_TSTRING`（reader 改为逐字节走）；
- 可选的结构化 `LOOP` 操作码，前提是性能分析显示有益；
- 紧凑的序列化格式和预编译的内置模块缓存。

## 9. 测试策略

| 层次 | 检查内容 |
|---|---|
| 虚拟机单元测试 | 每条操作码、环绕算术、边界检查、错误类型 |
| 模块验证 | 错误的寄存器/typecode/跳转目标会被拒绝 |
| Builder 往返 | `Module.to_dict()` / `from_dict()` 能复现代码 |
| 差分 | 对每个 fixture：Python 后端输出 == Python 虚拟机输出 |
| 融合 | 融合与未融合的模块产出完全相同的缓冲区 |
| 确定性 | 同一分支生成两次得到逐字节相同的模块 |
| 缓存 | 第二个进程直接加载模块而不重新生成 |

现有的 `tests/data/` 下 ROOT 文件和 `backend.use(...)` 上下文管理器已经提供了差分
测试框架；新后端只需接入 `read_branch_with_factory`。

## 10. 风险

| 风险 | 缓解措施 |
|---|---|
| 模块被缓存之后 ISA 还在变动 | 为模块格式做版本化；`isa_major` 不匹配就拒绝 |
| 前端复杂度随用户代码增长 | 严格子集 + 自动回退；Python 后端始终正确 |
| 融合漏掉热循环 | 当遍历已声明缓冲区的循环未被融合时给出警告；文档化典型形式 |
| Python 虚拟机慢到无法实用 | 它是开发工具；在 C++ 虚拟机落地之前，生产仍用 C++ 后端 |
| reader 改造破坏第三方 reader | `declare_*` 默认是空操作；旧 reader 在 Python 后端上继续可用 |

## 11. 待定事项

1. 未来的大版本中，`declare_*` 是否应当变成强制要求。
2. 生成的模块缓存在哪里，以及如何失效。
3. 子 reader 在前端内联与 `CALL` 之间究竟如何划分。
4. `read_body` 这类辅助方法应当发射为函数，还是由前端内联。
