# 06 · 依赖推断与 pip 镜像源

两个模块共同决定“装什么”和“从哪里装”：`app/dependency_inference.py` 与 `app/pip_mirror.py`，它们在 `ProcessManager.install_dependencies()` 中汇合。

## 1. 依赖来源与优先级

```text
上传脚本 main.py
   │  ast 静态分析
   ▼
推断依赖 inferred_dependencies  ─┐
                                 ├─ merge_dependencies() → pip install 参数
手动输入 manual_dependencies    ─┘        （手动依赖优先、按包名去重）
```

- **推断依赖**：上传时计算一次并持久化；之后不再自动重算。
- **手动依赖**：文本域原文保存在数据库，每次安装时重新解析。
- **合并规则**：手动依赖覆盖同名的推断依赖（例如手动写 `requests==2.32.3` 会替换推断出的 `requests`），顺序为“未被覆盖的推断依赖（保持推断列表原顺序，即按 import 名排序）→ 全部手动依赖（按输入顺序）”。

## 2. AST 推断细节

```python
tree = ast.parse(script_path.read_text(encoding="utf-8"))
imports = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        for alias in node.names:
            imports.add(alias.name.split(".", 1)[0])
    elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
        imports.add(node.module.split(".", 1)[0])
```

| 规则 | 例子 | 结果 |
| --- | --- | --- |
| `import a.b` 取首段 | `import os.path` | `os` |
| 绝对 `from x import y` | `from bs4 import BeautifulSoup` | `bs4` → `beautifulsoup4` |
| 相对导入忽略 | `from .local import f`（`level=1`） | 不产生依赖 |
| 标准库过滤 | `sys.stdlib_module_names` | `os`、`pathlib`、`json` 等被跳过 |
| 本地模块过滤 | 同目录 `*.py` 与含 `__init__.py` 的子目录 | 跳过，不误装 |
| 包名映射 | `KNOWN_IMPORT_TO_PACKAGE` | `cv2`→`opencv-python`、`PIL`→`Pillow`、`yaml`→`PyYAML`、`sklearn`→`scikit-learn`、`dotenv`→`python-dotenv`、`bs4`→`beautifulsoup4` |
| 输出顺序 | 按 import 名排序后映射 | 保证可预测、便于测试 |

**失败语义**：文件不是合法 Python 时 `ast.parse` 抛 `SyntaxError`；上传线程捕获后把应用置为 `error`，进度 `failed/100%`，`last_error` 为 `"Python syntax error: ..."`，且不会覆盖已存在的 `main.py`（解析发生在 `replace` 之前）。

**局限**：

- 不解析 `try/except ImportError` 的分支语义，所有字面 import 都会被收集（可能多装）。
- 动态导入（`__import__`、`importlib.import_module`）无法识别（可能少装）。
- 同名不同包、子模块直接作为包名等情况仍需依赖映射表或手动输入补足。

## 3. 手动依赖解析与合并

```python
parse_manual_dependencies(text)   # 去空白、跳过空行与 '#' 注释
merge_dependencies(inferred, manual_text)
_dependency_key(dep)              # 取包名首段，'_'→'-'，小写
```

示例（与测试一致）：

| 输入 | 输出 |
| --- | --- |
| 推断 `["requests", "rich"]`，手动 `"requests\nuvicorn"` | `["rich", "requests", "uvicorn"]` |
| 推断 `["requests", "python-dotenv"]`，手动 `"requests==2.32.3\npython_dotenv>=1"` | `["requests==2.32.3", "python_dotenv>=1"]` |
| 手动文本 `"\n# note\nrequests==2.32.3\n rich \n"` | `["requests==2.32.3", "rich"]` |

`_dependency_key` 的意义：`python_dotenv` 与 `python-dotenv` 视为同一包，避免 pip 参数重复或冲突。

> 手动依赖不做语法校验，直接拼进 `pip install` 参数列表（作为独立 argv 元素，不经过 shell，因此不存在命令注入；但非法的包规格会让 pip 失败并进入 `error` 状态）。

## 4. pip 镜像源

### 4.1 预设

| key | 标签 | URL |
| --- | --- | --- |
| `official` | PyPI 官方源 | `https://pypi.org/simple` |
| `tsinghua` | 清华大学 | `https://pypi.tuna.tsinghua.edu.cn/simple` |
| `aliyun` | 阿里云 | `https://mirrors.aliyun.com/pypi/simple` |
| `tencent` | 腾讯云 | `https://mirrors.cloud.tencent.com/pypi/simple` |
| `ustc` | 中国科学技术大学 | `https://pypi.mirrors.ustc.edu.cn/simple` |
| `custom` | 自定义 | 由用户输入 |

`custom` 的预设 URL 为空串，实际值来自设置项 `pip_index_url`。

### 4.2 校验与规范化

`validate_mirror_url(url)` 返回 `(ok, message)`：

| 输入 | 结果 |
| --- | --- |
| 空串/全空白 | `False`，"自定义镜像源 URL 不能为空。" |
| `notaurl` | `False`，"镜像源 URL 必须以 http:// 或 https:// 开头。" |
| `https://`（无 host） | `False`，"镜像源 URL 缺少主机名。" |
| `https://pypi.org/simple` | `True`，`""` |
| `http://mirrors.intra:8081/simple` | `True`（允许内网 http） |

`normalize_mirror_url` 仅 `strip()` 并去掉**末尾所有** `/`。

### 4.3 生成 pip 参数

```python
build_pip_index_args("")
# → []

build_pip_index_args("https://mirrors.aliyun.com/pypi/simple")
# → ["-i", "https://mirrors.aliyun.com/pypi/simple"]

build_pip_index_args("http://mirrors.intra:8081/simple/")
# → ["-i", "http://mirrors.intra:8081/simple",
#    "--trusted-host", "mirrors.intra:8081"]
```

规则：

- 空 URL → 不追加任何参数，pip 使用默认官方源（保证“未配置时行为不变”）。
- https → 只加 `-i`。
- http → 额外 `--trusted-host <netloc>`（含端口），避免 pip 拒绝非 HTTPS 源。

### 4.4 配置链路

```text
GET /settings
  → repo.get_setting("pip_index_selector", "official")
  → repo.get_setting("pip_index_url", "")  （仅 custom 时展示）
  → 渲染预设 + 当前生效 URL

POST /settings (source, custom_url)
  → custom: validate_mirror_url → normalize
  → preset: selector_url(source, custom_url)
  → 未知: 400
  → repo.set_setting("pip_index_selector", source)
    repo.set_setting("pip_index_url", url)

ProcessManager.install_dependencies()
  → repo.get_setting("pip_index_url", "")
  → build_pip_index_args(url)
  → pip install <deps> ...args
```

设置保存在 SQLite（`app_settings`），立即对所有后续安装/重启生效，无需重启服务。

## 5. 安装命令完整示例

假设应用推断依赖 `["requests", "beautifulsoup4"]`，手动依赖 `"requests==2.32.3"`，镜像为阿里云：

```text
<app_dir>/.venv/bin/python -m pip install \
  beautifulsoup4 requests==2.32.3 \
  -i https://mirrors.aliyun.com/pypi/simple
```

（实际 argv 中依赖是独立元素，顺序如上；输出写入 `<app_dir>/install.log`。）

## 6. 测试覆盖

| 测试文件 | 覆盖点 |
| --- | --- |
| `tests/test_dependency_inference.py` | 标准库/本地模块过滤、包名映射、注释与空行、去重与顺序、版本覆盖 |
| `tests/test_pip_mirror.py` | 设置项默认值/upsert、URL 校验、`-i` 与 `--trusted-host`、规范化 |
| `tests/test_settings.py` | 设置页渲染、鉴权、保存预设、拒绝非法自定义 URL、pip 命令拼装（mock `subprocess.run`） |
