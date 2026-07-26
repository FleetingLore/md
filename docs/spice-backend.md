# SPICE + SchemDraw 后端复现指南

## 1. 系统要求

| 组件 | 最低版本 | 用途 |
|------|----------|------|
| Python | ≥ 3.9 | 运行 MkDocs 及所有 macro |
| ngspice | ≥ 40 | SPICE 仿真引擎（可选，缺则只展示网表） |
| matplotlib | ≥ 3.5 | 绘制 Bode 图、瞬态波形（可选） |
| numpy | ≥ 1.21 | 数值计算（matplotlib 依赖） |
| SchemDraw | ≥ 0.19 | 程序化电路图绘制（可选） |

---

## 2. 一键安装

```bash
# macOS
brew install ngspice
pip install mkdocs-macros-plugin matplotlib numpy schemdraw[svg]

# Ubuntu / Debian
apt install ngspice
pip install mkdocs-macros-plugin matplotlib numpy schemdraw[svg]
```

> 注意：`schemdraw[svg]` 需要系统已安装 `cairo` 库。
> Ubuntu: `apt install libcairo2-dev`
> macOS: 通常 Xcode CLT 自带。

---

## 3. 项目文件结构

```
md/                          # 项目根
├── mkdocs.yml               # MkDocs 配置（插件、macro 模块名）
├── Makefile                 # 构建/部署脚本
├── requirements.txt         # Python 依赖清单
│
├── macros.py                # ★ 核心后端 —— 所有 SPICE + 电路图 macro
├── macros_schemdraw.py      # ★ SchemDraw 渲染模块（被 macros.py import）
│
├── circuits/                # SchemDraw 电路定义（Python 脚本）
│   └── examples.py          #   lc_series(), rlc_series() 等函数
│
├── docs/                    # MkDocs 文档根
│   ├── 0.md                 #   LC 电路示例（含 spice/bode/tran/sch 调用）
│   ├── 1.md ... 11.md       #   各章节
│   ├── spice-backend.md     #   本文
│   ├── stylesheets/
│   │   └── extra.css        #   SPICE block UI 样式
│   └── javascripts/
│       ├── mathjax.js
│       └── spice-enhance.js #   裸 ```spice 代码块 toolbar 增强
│
└── site/                    # 构建产物（mkdocs build 生成，可 .gitignore）
```

---

## 4. mkdocs.yml 关键配置

```yaml
# ---- 插件 ----
plugins:
  - search
  - macros:                    # mkdocs-macros-plugin
      module_name: macros      # → 加载项目根目录的 macros.py

# ---- Markdown 扩展 ----
markdown_extensions:
  - pymdownx.arithmatex:       # LaTeX 数学公式
      generic: true
  - pymdownx.superfences       # ``` 代码块增强

# ---- 外部 JS ----
extra_javascript:
  - javascripts/mathjax.js
  - https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js
  - javascripts/spice-enhance.js   # spice 代码块 toolbar
```

**关键点**：`plugins.macros.module_name: macros` 告诉 MkDocs 在构建时加载 `macros.py` 并执行其中的 `define_env(env)` 函数。

---

## 5. macros.py —— 核心后端

### 5.1 加载机制

`mkdocs-macros-plugin` 在构建每个页面时：

1. 加载 `macros.py` 中的 `define_env(env)` 函数
2. 扫描 Markdown 中的 `{{ macro() }}` 和 `{% call macro() %}...{% endcall %}`
3. 调用对应的 Python 函数，将返回值插入页面 HTML

### 5.2 注册的 Macro

| Macro | 语法 | 功能 |
|-------|------|------|
| `spice(title)` | `{% call spice(title="标题") %}` | ngspice 仿真，自动补全 `.print` |
| `bode(node, label)` | `{% call bode(node="v(2)", label="标题") %}` | AC 分析 → Bode 图 |
| `tran(node, label)` | `{% call tran(node="v(2)", label="标题") %}` | 瞬态分析 → 波形图 |
| `circuit(data)` | `{{ circuit("base64...") }}` | CircuitJS 交互式 iframe |
| `sch(name)` | `{{ sch("examples.lc_series") }}` | SchemDraw 电路图 |

### 5.3 核心函数调用链

```
Markdown
  │
  ├─ {{ spice(title="LC") }}
  │   └─ _resolve_netlist(netlist, caller)    # 提取 {% call %} 正文
  │   └─ _spice_details(escaped, ok, title)   # 生成 HTML（toolbar + code）
  │
  ├─ {{ sch("examples.lc_series") }}
  │   └─ macros_schemdraw.schemdraw_svg()     # 动态导入 circuits/examples.py
  │
  ├─ {{ circuit("base64") }}
  │   └─ 直接拼接 <iframe> HTML
  │
  └─ Toolbar 按钮（纯前端 JS，在 spice-enhance.js 中）
      · Copy — 复制网表到剪贴板
      · 数据 — data: URI 新窗口查看
      · Bode / 瞬态 — 调用后端 API 或打开在线工具
      · 编辑 — 就地编辑网表文字
```

### 5.4 ngspice 交互（_run_ngspice）

```python
def _run_ngspice(netlist: str, cwd=None, auto_print=True):
    mod = _auto_add_print(netlist) if auto_print else netlist
    r = subprocess.run(
        ["ngspice", "-b"],          # -b = batch mode
        input=mod,                   # stdin 管道传入网表
        capture_output=True, text=True,
        timeout=30, cwd=cwd
    )
    return r.stdout, r.stderr, r.returncode == 0
```

**关键点**：

- `-b`（batch）模式要求网表包含 `.print` 指令 → `_auto_add_print()` 自动补全
- 使用 **stdin 管道**而非临时文件，避免权限和路径问题
- 30 秒超时防止仿真死循环
- `FileNotFoundError` → 返回友好提示而非崩溃

### 5.5 matplotlib 绘图（_make_bode_svg / _make_tran_svg）

```python
# Bode 图
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 5),
                                sharex=True, constrained_layout=True)

# 颜色常量（与站点 CSS 同步）
C_BG    = "#737373"   # 背景色
C_TEXT  = "#cacaca"   # 文字 / 坐标轴
C_THEME = "#6cffca"   # 幅值曲线（青绿）
C_LINK  = "#8bf5ff"   # 相位曲线（浅蓝）

# 输出为 base64 SVG
buf = io.BytesIO()
fig.savefig(buf, format="svg", dpi=100,
            facecolor=C_BG, bbox_inches="tight")
```

**关键点**：

- `constrained_layout=True` 替代 `tight_layout()`，自动收紧边距
- `bbox_inches='tight'` 裁掉 SVG 右边多余空白
- 输出到 `io.BytesIO()` 内存流，不写磁盘
- 颜色常量集中定义在文件顶部，便于全局调整

### 5.6 data URI 编码

所有图片和文本内嵌为 `data:` URI，**零文件依赖**：

```python
# 文本
def _data_uri(text, mime="text/plain"):
    return f"data:{mime};base64,{base64.b64encode(text.encode()).decode()}"

# SVG 图片
def _svg_uri(b: bytes):
    return f"data:image/svg+xml;base64,{base64.b64encode(b).decode()}"
```

**好处**：站点是纯静态 HTML，不依赖 `mkdocs serve` 的文件服务能力，任意 HTTP 服务器均可部署。

---

## 6. macros_schemdraw.py —— SchemDraw 电路图

```python
def schemdraw_svg(project_dir: str, name: str) -> str:
    # 1. 解析 "examples.lc_series" → 模块名 + 函数名
    mod_name, func_name = name.rsplit('.', 1)

    # 2. 动态导入 circuits/<mod_name>.py
    circuits = str(Path(project_dir) / 'circuits')
    sys.path.insert(0, circuits)
    mod = importlib.import_module(mod_name)

    # 3. 调用函数，获取 Drawing 对象
    d = getattr(mod, func_name)()

    # 4. 导出 SVG，替换颜色匹配站点主题
    svg = d.get_imagedata('svg')
    svg = svg.replace(b'fill: #ffffff', b'fill: #737373')
    svg = svg.replace(b'stroke: #000000', b'stroke: #cacaca')

    # 5. 返回 base64 data URI
    return f"data:image/svg+xml;base64,{base64.b64encode(svg).decode()}"
```

**电路定义示例**（`circuits/examples.py`）：

```python
import schemdraw
from schemdraw import elements as elm

def lc_series():
    d = schemdraw.Drawing()
    d += elm.SourceSin().label('$V_s$')
    d += elm.Inductor().right().label('L')
    d += elm.Capacitor().right().label('C')
    d += elm.Line().down()
    d += elm.Line().left()
    return d
```

在 Markdown 中调用：

```markdown
{{ sch("examples.lc_series") }}
```

→ 构建时渲染为 SVG，以 base64 data URI 嵌入页面。

---

## 7. 前端 JS（spice-enhance.js）

为手写的裸 ` ```spice ` 代码块注入 toolbar（Copy / Open in ngspice.com 按钮）。

```javascript
document$.subscribe(() => {
  document.querySelectorAll("code.language-spice").forEach((code) => {
    enhanceBlock(code);
  });
});
```

**注意**：宏生成的块自带 toolbar，JS 会跳过 `.spice-block` 容器内的代码块，避免重复。

---

## 8. 配色同步

站点主题色定义在两个地方，修改时需保持同步：

| 位置 | 变量 |
|------|------|
| `docs/stylesheets/extra.css` | `:root { --bg: #737373; --text: #ffffff; --theme: #6cffca; ... }` |
| `macros.py` 顶部 | `C_BG = "#737373"` `C_TEXT = "#cacaca"` `C_THEME = "#6cffca"` 等 |

Plot 的轴、文字、网格颜色均从 `macros.py` 读取，与 CSS 无关。

---

## 9. 构建与部署

```bash
# 本地开发
make serve        # mkdocs serve，http://localhost:8000/md/

# 生产构建
make build        # mkdocs build → site/

# 部署（rsync 到服务器）
make deploy       # HOST/DIR 在 Makefile 顶部配置
```

**服务器要求**：纯静态文件，nginx/apache 即可，无需 Python/ngspice 运行时。所有仿真在构建时完成，结果已内嵌在 HTML 中。

---

## 10. 在新服务器上复现

### 10.1 最小安装（只需构建，不要仿真图）

```bash
git clone <repo>
cd md
pip install mkdocs-material mkdocs-macros-plugin schemdraw[svg]
make build
```

此时 `spice()` / `bode()` / `tran()` 会降级展示网表（不跑仿真），`sch()` 正常渲染电路图。

### 10.2 完整安装（仿真图 + Bode 图）

```bash
git clone <repo>
cd md

# 系统依赖
brew install ngspice            # macOS
# 或: apt install ngspice      # Ubuntu

# Python 依赖
pip install -r requirements.txt

make build
```

### 10.3 常见问题

| 症状 | 原因 | 解决 |
|------|------|------|
| `ngspice not found` | ngspice 未安装 | `brew install ngspice` |
| `no .print/.plot/.fourier` | 网表缺少输出指令 | `_auto_add_print()` 应自动补全；检查宏版本 |
| plot 右边大片灰色 | matplotlib 边距未收紧 | 确保 `constrained_layout=True` + `bbox_inches='tight'` |
| SVG 颜色与页面不一致 | 颜色常量不同步 | 检查 `macros.py` 顶部 `C_BG` 等是否与 `extra.css` 一致 |
| `ModuleNotFoundError: macros_schemdraw` | 缺少依赖 | `pip install schemdraw[svg]` |
| schemdraw SVG 白底黑线 | 颜色替换未生效 | 检查 `schemdraw_svg()` 中 `.replace()` 调用 |
