# 02 · 模块职责

本文按源码文件逐一说明职责、对外接口与协作关系。所有路径相对于仓库根目录。

---

## 2.1 `app/config.py` — 配置加载

**职责**：把 `config.toml` 解析为冻结的 `Settings`，并在启动早期快速失败。

**核心对象**

| 名称 | 类型 | 说明 |
| --- | --- | --- |
| `DEFAULT_CONFIG_PATH` | `Path("config.toml")` | 相对**当前工作目录**，因此必须在项目根目录（或挂载了 config 的目录）启动 |
| `Settings` | `@dataclass(frozen=True)` | `data_dir`、`db_path`、`admin_password`、`secret_key` |
| `load_settings(config_path)` | 函数 | 读取 TOML 并校验 |

**行为要点**

- 配置文件不存在 → `RuntimeError("Configuration file not found: ...")`。
- `data_dir` 默认 `data`，`db_path` 默认 `<data_dir>/manager.db`，两者都 `.resolve()` 为绝对路径。
- `admin_password` 去空白后为空 → `RuntimeError`（阻止无密码启动）。
- `secret_key` 缺省时使用 `secrets.token_urlsafe(32)`：**每次启动随机**，导致重启后旧会话失效（README 已说明）。

**相关测试**：[`tests/test_config.py`](../../tests/test_config.py)

---

## 2.2 `app/models.py` — 数据模型

**职责**：定义跨层共享的只读应用快照。

```python
@dataclass(frozen=True)
class ManagedApp:
    id: int
    name: str
    slug: str
    script_name: str | None
    manual_dependencies: str
    inferred_dependencies: str
    status: str
    desired_running: bool
    pid: int | None
    last_error: str
    progress_stage: str
    progress_percent: int
    progress_message: str
    created_at: str
    updated_at: str
```

**派生属性**

- `inferred_list`：按行切分 `inferred_dependencies`，去空行 → `list[str]`。
- `manual_list`：按行切分 `manual_dependencies`，去空行 → `list[str]`。

模板、路由 JSON 响应与 `ProcessManager` 都直接消费这些属性，避免在展示层重复解析字符串。依赖表达式（如 `requests==2.32.3`）原样保留。

---

## 2.3 `app/database.py` — SQLite 仓库层

**职责**：schema 初始化/迁移、应用元数据 CRUD、全局设置项读写。

**常量**

- `PIP_INDEX_URL_SETTING_KEY = "pip_index_url"`
- `PIP_INDEX_SELECTOR_SETTING_KEY = "pip_index_selector"`

**类 `AppRepository`**

| 方法 | 说明 |
| --- | --- |
| `__init__(db_path)` | 创建父目录并调用 `init_schema()` |
| `connect()` | 新建 `sqlite3.Connection`，`row_factory = sqlite3.Row`（每次操作独立连接，依赖上下文管理器提交） |
| `init_schema()` | 建 `managed_apps` / `app_settings` 两表；对旧库补齐 3 个 progress 列 |
| `_ensure_column(conn, column, definition)` | 读取 `PRAGMA table_info` 后按需 `ALTER TABLE ... ADD COLUMN` |
| `list_apps()` | 按 `updated_at DESC, id DESC` 排序返回全部应用 |
| `get_app(app_id)` | 主键查询，未命中返回 `None` |
| `get_app_by_slug(slug)` | slug 查询（当前路由未使用，供扩展） |
| `create_app(name)` | 生成唯一 slug（冲突追加 `-2`、`-3`…），插入后回读 |
| `update_upload(app_id, script_name, manual_dependencies, inferred_dependencies)` | 写脚本名/依赖，状态置 `installing`，清空 `last_error` |
| `set_status(app_id, status, last_error="", pid=None)` | 更新状态、错误信息与 PID |
| `set_progress(app_id, stage, percent, message)` | 进度三元组，百分比截断到 `[0, 100]` |
| `set_desired_running(app_id, desired)` | 期望状态（布尔存为 0/1） |
| `delete_app(app_id)` | 删除记录（不删文件，文件由 `ProcessManager.delete` 处理） |
| `get_setting(key, default="")` | 读设置项 |
| `set_setting(key, value)` | `INSERT ... ON CONFLICT(key) DO UPDATE` 幂等 upsert |
| `_row_to_app(row)` | `sqlite3.Row` → `ManagedApp`（含类型转换） |

**模块级函数 `slugify(value)`**：小写、非字母数字替换为 `-`、去首尾 `-`；空结果回退 `"app"`。

**注意点**

- 无显式事务管理，依靠 `with self.connect() as conn:` 的自动提交/回滚语义。
- 时间字段由 SQLite `CURRENT_TIMESTAMP` 维护（UTC 文本）。
- 迁移只增列、不删列，向后兼容优先。

**相关测试**：`tests/test_database.py`、`tests/test_pip_mirror.py`（设置项部分）

---

## 2.4 `app/dependency_inference.py` — 依赖推断

**职责**：从上传脚本的 `import` 静态分析出第三方包，并与手动依赖合并。

**常量 `KNOWN_IMPORT_TO_PACKAGE`**：导入名 → PyPI 包名映射，当前 6 项：

| import | package |
| --- | --- |
| `bs4` | `beautifulsoup4` |
| `cv2` | `opencv-python` |
| `dotenv` | `python-dotenv` |
| `PIL` | `Pillow` |
| `sklearn` | `scikit-learn` |
| `yaml` | `PyYAML` |

**函数**

| 函数 | 行为 |
| --- | --- |
| `infer_dependencies(script_path)` | `ast.parse` 后遍历：`Import` 取 `alias.name` 首段；`ImportFrom` 仅接受 `level == 0`（忽略相对导入）；过滤标准库（`sys.stdlib_module_names`）与同目录本地模块；按 **import 名排序**后映射为包名返回 |
| `parse_manual_dependencies(text)` | 逐行去空白，跳过空行与 `#` 注释 |
| `merge_dependencies(inferred, manual_text)` | 手动依赖优先：先输出“不在手动键集合中”的推断依赖，再输出全部手动依赖；按 `_dependency_key` 去重并保持顺序 |
| `_dependency_key(dep)` | 取包名首段，`_`→`-`，小写，用于判定 `python_dotenv` 与 `python-dotenv` 等价 |
| `_local_modules(directory)` | 目录下 `*.py` 的 stem + 含 `__init__.py` 的子目录名，视为本地模块而不装包 |

**能力边界**：这是“尽力而为”的推断。动态导入（`importlib`）、条件导入之外的别名、包名与导入名不一致的库（除映射表外）都可能误判，因此 UI 提供手动依赖输入框作为补充/覆盖手段。

**相关测试**：`tests/test_dependency_inference.py`

---

## 2.5 `app/pip_mirror.py` — pip 镜像源

**职责**：镜像源预设、URL 校验/规范化、生成 `pip install` 参数。

**数据**

- `OFFICIAL_INDEX = "https://pypi.org/simple"`
- `PipMirrorPreset(key, label, url)`：不可变 dataclass。
- `PIP_MIRROR_PRESETS`：官方、清华、阿里云、腾讯云、中科大、自定义（url 为空串）。
- `_PRESET_BY_KEY`：key → preset 的索引。

**函数**

| 函数 | 说明 |
| --- | --- |
| `get_preset(key)` | 未命中返回 `None` |
| `normalize_mirror_url(url)` | `strip()` + 去掉末尾 `/` |
| `validate_mirror_url(url)` | 要求非空、scheme ∈ {http, https}、有 `netloc`；返回 `(bool, 中文错误信息)` |
| `build_pip_index_args(url)` | 空 URL → `[]`；否则 `["-i", url]`；若为 `http` 且含 host，追加 `["--trusted-host", netloc]` |
| `selector_url(selector, custom_url)` | `custom` 返回规范化自定义 URL；否则查预设，未命中返回 `""` |

**相关测试**：`tests/test_pip_mirror.py`、`tests/test_settings.py`

---

## 2.6 `app/process_manager.py` — 进程与运行时管理

**职责**：应用目录布局、venv 创建、依赖安装、子进程生命周期、日志读取、启动恢复。是系统中最“重”的模块。

**目录约定（`data_dir/apps/<slug>/`）**

| 路径 | 用途 |
| --- | --- |
| `main.py` | 上传脚本固定落点 |
| `.venv/` | 应用专属虚拟环境 |
| `.venv/bin/python` | 运行脚本的解释器（`venv_python()`） |
| `install.log` | venv 创建 + pip install 输出（追加） |
| `runtime.log` | 应用 stdout/stderr（追加，`Popen` 直接重定向） |
| `.pending-upload-<uuid>.py` | 上传临时文件，处理结束删除 |

**类 `ProcessManager`**

| 方法 | 说明 |
| --- | --- |
| `__init__(repo, data_dir)` | 保存 `processes: dict[int, Popen]`、`RLock`，确保 data_dir 存在 |
| `app_dir(app)` | 返回并创建 `data/apps/<slug>` |
| `script_path(app)` / `log_path(app)` / `install_log_path(app)` / `venv_python(app)` | 路径计算 |
| `start(app_id, install=True, progress=None)` | 先停旧进程；按需装依赖；`Popen` 启动；写状态/进度；启动 `_watch_process` 线程 |
| `stop(app_id, desired=False, reset_progress=True)` | 优先杀内存中的进程；否则尝试 `_stop_persisted_process`（数据库中残留 pid）；成功则写 `stopped` |
| `restart(app_id)` | 等价于 `start(install=True)` |
| `delete(app_id)` | 先停止，再 `rmtree` 应用目录，最后删数据库记录 |
| `restore_desired()` | 遍历 `desired_running=1` 的应用，`start(install=False)`；单个失败不影响其他 |
| `shutdown()` | 停止所有内存中进程，**`desired=True`**，以便下次启动恢复 |
| `install_dependencies(app, progress=None)` | venv 不存在则创建；有依赖则 pip install（附加镜像参数）；失败置 `error` 并返回 `False` |
| `read_log_tail(app, limit=20000)` | 依次读取 `install.log`、`runtime.log` 的末尾 `limit` 字节，UTF-8 容错解码后用换行拼接 |
| `_watch_process(app_id, process)` | 阻塞 `wait()`，清理字典；若“期望运行且退出码≠0”标 `error`，否则 `stopped` |
| `_stop_persisted_process(app_id)` | 对数据库中的 pid 执行 `killpg(SIGTERM)`，`waitpid` 失败时轮询进程组最多 5 秒，再 `SIGKILL` |
| `_require_app(app_id)` | 不存在抛 `ValueError` |
| `_progress(progress, ...)` | 回调保护（回调可为 `None`） |

**并发与安全**

- `start`/`stop`/`delete`/`shutdown` 全部在 `self.lock`（`RLock`）内，上传线程也显式持有同一把锁。
- 启动前**总是先 stop**，保证同一应用不会出现两个实例。
- `start_new_session=True` + `os.killpg` 保证清理整棵子进程树。
- 停止采用 5 秒 SIGTERM 宽限 + 5 秒等待 SIGKILL，并区分 `ProcessLookupError`（已退出，视为成功）与 `PermissionError`（写入错误状态，返回失败）。

**已知限制**

- `processes` 只记录当前 Python 进程启动的子进程；服务重启后靠数据库 `pid` + `killpg` 兜底。
- 路径硬编码 POSIX 的 `bin/python`，Windows 不适用。
- 日志读取为同步文件 I/O，超大日志只取尾部 20KB。

**相关测试**：`tests/test_process_manager.py`、`tests/test_settings.py`

---

## 2.7 `app/main.py` — FastAPI 接入层

**职责**：应用装配、会话鉴权、页面与 JSON API、上传编排、异常映射。

**模块级单例**（导入时创建）

```python
settings = load_settings()
repo = AppRepository(settings.db_path)
manager = ProcessManager(repo, settings.data_dir)
APP_DIR = Path(__file__).resolve().parent
```

这意味着**导入 `app.main` 需要当前目录存在 `config.toml`**，也解释了测试中先 `monkeypatch.chdir(tmp_path)` 再 `importlib.reload(app.main)` 的写法。

**应用装配**

- `lifespan`：启动时 `manager.restore_desired()`，关闭时 `manager.shutdown()`。
- `SessionMiddleware(secret_key=..., same_site="lax")`。
- `/static` 挂载 `app/static`，SPA 构建产物位于 `app/static/app/`；兜底路由返回 `index.html`。

**鉴权辅助**

| 函数 | 行为 |
| --- | --- |
| `is_authenticated(request)` | 读取会话中的 `authenticated` |
| `require_auth(request)` | 未登录抛 401（异常处理器转 `{"error": ...}` JSON） |

**异常处理器**：`http_exception_handler` 把 `HTTPException` 统一转为 `{"error": detail}`；`validation_exception_handler` 把请求体校验失败转为 422 中文错误。

**上传编排**

- `_process_uploaded_script(app_id, pending_path, manual_dependencies)`：在后台线程中持锁执行“停止 → 推断 → 落盘 → 写库 → 启动”，并捕获 `SyntaxError` 与通用异常写入 `error` 状态与 100% 失败进度。
- 上传接口现在只返回 JSON `{"accepted": true, "app_id": id}`，不再存在表单重定向分支。

路由细节见 [05 Web 接口与前端](05-web-api.md)。

---

## 2.8 `frontend/` 与 `app/static/app/`

前端是独立的 React + TypeScript 工程：

| 路径 | 职责 |
| --- | --- |
| `frontend/src/pages/LoginPage.tsx` | 管理员登录表单与已登录重定向 |
| `frontend/src/pages/DashboardPage.tsx` | 应用侧栏、详情摘要、上传/控制/日志布局 |
| `frontend/src/pages/SettingsPage.tsx` | pip 镜像源预设、自定义 URL、保存与生效预览 |
| `frontend/src/components/apps/` | `AppSidebar`、`UploadCard`、`ControlCard`、`LogsCard` |
| `frontend/src/components/ui/` | Button、Card、Field、StatusBadge、ProgressBar、ConfirmDialog 等 |
| `frontend/src/lib/api.ts` | 类型化 `fetch` 客户端、`ApiError`、401 跳转 |
| `frontend/src/lib/queries.ts` | TanStack Query hooks、轮询间隔、XHR 上传进度 |
| `frontend/src/lib/format.ts` | 状态/进度阶段中文映射、时间格式化 |
| `frontend/src/test/` | Vitest + Testing Library 页面渲染测试 |
| `app/static/app/` | `npm run build` 生成的 SPA 产物（gitignore） |

构建配置：Vite `base=/static/app/`，默认输出到 `../app/static/app`；Docker 中通过 `BUILD_OUT_DIR=dist` 输出后复制到运行镜像。开发模式 Vite 监听 `5173`，把 `/api` 代理到 `127.0.0.1:7999`。

---

## 2.9 模块协作一览

| 场景 | 参与模块 |
| --- | --- |
| SPA 页面 | 浏览器 → FastAPI 兜底路由返回 `index.html` → React Router + TanStack Query → `/api/*` |
| 创建应用 | `main.py` → `database.create_app` → `manager.app_dir` |
| 上传处理 | `main.py` 线程 → `manager.stop/start`、`dependency_inference.infer_dependencies`、`database.update_upload` |
| 启动/重启 | `main.py` → `manager.start` → `install_dependencies`（`pip_mirror.build_pip_index_args`、`merge_dependencies`） |
| 镜像设置 | `main.py` → `pip_mirror.validate/normalize/selector_url` → `database.set_setting` |
| 重启恢复 | `lifespan` → `manager.restore_desired` → `database.list_apps` + `manager.start` |
