# 08 · 关键类与函数索引

按模块列出公开接口的签名、参数、返回值与副作用，便于快速定位与调用。签名与源码一致（`from __future__ import annotations` 已启用）。

---

## `app.config`

### `@dataclass(frozen=True) class Settings`

| 字段 | 类型 |
| --- | --- |
| `data_dir` | `Path`（绝对路径） |
| `db_path` | `Path`（绝对路径） |
| `admin_password` | `str` |
| `secret_key` | `str` |

### `load_settings(config_path: Path | str = Path("config.toml")) -> Settings`

- 读取 TOML；缺文件或密码为空抛 `RuntimeError`。
- `secret_key` 缺失时生成随机值。
- 副作用：无（只读文件）。

---

## `app.models`

### `@dataclass(frozen=True) class ManagedApp`

字段见 [03 数据模型](03-data-model.md#2-字段语义)。派生属性：

| 属性 | 返回 | 说明 |
| --- | --- | --- |
| `inferred_list` | `list[str]` | 推断依赖按行拆分去空 |
| `manual_list` | `list[str]` | 手动依赖按行拆分去空 |

---

## `app.database`

### 常量

- `PIP_INDEX_URL_SETTING_KEY: str = "pip_index_url"`
- `PIP_INDEX_SELECTOR_SETTING_KEY: str = "pip_index_selector"`

### `class AppRepository`

```python
def __init__(self, db_path: Path) -> None
def connect(self) -> sqlite3.Connection
def init_schema(self) -> None
def _ensure_column(self, conn: sqlite3.Connection, column: str, definition: str) -> None
def list_apps(self) -> list[ManagedApp]
def get_app(self, app_id: int) -> ManagedApp | None
def get_app_by_slug(self, slug: str) -> ManagedApp | None
def create_app(self, name: str) -> ManagedApp
def update_upload(self, app_id: int, script_name: str,
                  manual_dependencies: str, inferred_dependencies: list[str]) -> None
def set_status(self, app_id: int, status: str,
               last_error: str = "", pid: int | None = None) -> None
def set_progress(self, app_id: int, stage: str, percent: int, message: str) -> None
def set_desired_running(self, app_id: int, desired: bool) -> None
def delete_app(self, app_id: int) -> None
def get_setting(self, key: str, default: str = "") -> str
def set_setting(self, key: str, value: str) -> None
def _row_to_app(self, row: sqlite3.Row) -> ManagedApp
```

行为摘要：

| 方法 | 返回/副作用 |
| --- | --- |
| `create_app` | 插入记录并回读；slug 冲突自动加 `-2`、`-3`；名称 `strip()` |
| `update_upload` | 写脚本名/依赖，`status='installing'`，清空 `last_error` |
| `set_status` | **总是**同时写 `pid`（未传则置 `NULL`）与 `last_error` |
| `set_progress` | `percent` 截断到 `[0,100]` |
| `set_setting` | upsert（`ON CONFLICT(key) DO UPDATE`）并更新 `updated_at` |

### `slugify(value: str) -> str`

小写 → 非字母数字替换 `-` → 去首尾 `-`；空结果返回 `"app"`。

---

## `app.dependency_inference`

```python
KNOWN_IMPORT_TO_PACKAGE: dict[str, str]

def infer_dependencies(script_path: Path) -> list[str]
def parse_manual_dependencies(text: str) -> list[str]
def merge_dependencies(inferred: list[str], manual_text: str) -> list[str]
def _dependency_key(dependency: str) -> str
def _local_modules(directory: Path) -> set[str]
```

| 函数 | 返回 | 可能异常 |
| --- | --- | --- |
| `infer_dependencies` | 排序去重后的包名列表 | `SyntaxError`（非法 Python）、`OSError`（读取失败） |
| `parse_manual_dependencies` | 去空行/注释后的行列表 | — |
| `merge_dependencies` | 手动优先、按 key 去重的合并列表 | — |

`_dependency_key` 规则：`\s*([A-Za-z0-9_.-]+)` 取包名，`_`→`-`，小写。

---

## `app.pip_mirror`

```python
OFFICIAL_INDEX: str
@dataclass(frozen=True) class PipMirrorPreset: key: str; label: str; url: str
PIP_MIRROR_PRESETS: list[PipMirrorPreset]

def get_preset(key: str) -> PipMirrorPreset | None
def normalize_mirror_url(url: str) -> str
def validate_mirror_url(url: str) -> tuple[bool, str]
def build_pip_index_args(url: str) -> list[str]
def selector_url(selector: str, custom_url: str) -> str
```

| 函数 | 纯函数 | 说明 |
| --- | --- | --- |
| `get_preset` | 是 | O(1) 查字典 |
| `normalize_mirror_url` | 是 | 去空白与尾部 `/` |
| `validate_mirror_url` | 是 | `(True, "")` 或 `(False, 中文消息)` |
| `build_pip_index_args` | 是 | 返回 `[]` 或 `["-i", url]`（http 再补 `--trusted-host`） |
| `selector_url` | 是 | `custom` 取自定义值；未知预设返回 `""` |

---

## `app.process_manager`

### `class ProcessManager`

```python
def __init__(self, repo: AppRepository, data_dir: Path) -> None
def app_dir(self, app: ManagedApp) -> Path
def script_path(self, app: ManagedApp) -> Path | None
def log_path(self, app: ManagedApp) -> Path
def install_log_path(self, app: ManagedApp) -> Path
def venv_python(self, app: ManagedApp) -> Path
def start(self, app_id: int, install: bool = True,
          progress: Callable[[str, int, str], None] | None = None) -> None
def stop(self, app_id: int, desired: bool = False,
         reset_progress: bool = True) -> bool
def restart(self, app_id: int) -> None
def delete(self, app_id: int) -> None
def restore_desired(self) -> None
def shutdown(self) -> None
def install_dependencies(self, app: ManagedApp,
                         progress: Callable[[str, int, str], None] | None = None) -> bool
def read_log_tail(self, app: ManagedApp, limit: int = 20000) -> str
def _watch_process(self, app_id: int, process: subprocess.Popen[bytes]) -> None
def _stop_persisted_process(self, app_id: int) -> bool
def _require_app(self, app_id: int) -> ManagedApp
def _progress(self, progress: Callable[[str, int, str], None] | None,
              stage: str, percent: int, message: str) -> None
```

**实例属性**

| 属性 | 类型 | 说明 |
| --- | --- | --- |
| `repo` | `AppRepository` | 状态持久化 |
| `data_dir` | `Path` | 数据根目录 |
| `processes` | `dict[int, Popen[bytes]]` | 仅当前进程启动的子进程 |
| `lock` | `threading.RLock` | 进程操作与上传串行化 |

**返回值/异常语义**

| 方法 | 返回 | 失败表现 |
| --- | --- | --- |
| `start` | `None` | 除应用不存在抛 `ValueError` 外不抛业务异常；缺脚本/停止失败/安装失败时写 `error` 并 return |
| `stop` | `bool` | `False` 表示无法停止（写 `error`） |
| `install_dependencies` | `bool` | `False` 表示 venv/pip 失败（写 `error`） |
| `read_log_tail` | `str` | 文件不存在时返回空串/仅存在的部分 |
| `_require_app` | `ManagedApp` | 不存在抛 `ValueError` |
| `delete` | `None` | 停止失败则不做任何删除 |

**`progress` 回调约定**：`(stage: str, percent: int, message: str) -> None`；`None` 时回退为写数据库。

---

## `app.main`

### 模块级对象

| 名称 | 类型 | 生命周期 |
| --- | --- | --- |
| `settings` | `Settings` | 导入时创建 |
| `repo` | `AppRepository` | 导入时创建 |
| `manager` | `ProcessManager` | 导入时创建 |
| `APP_DIR` | `Path` | `app/` 目录 |
| `FRONTEND_INDEX` | `Path` | `app/static/app/index.html`（Vite 构建产物） |
| `app` | `FastAPI` | `title="Python Management Platform"`，注册 lifespan 与 SessionMiddleware |

### 生命周期与鉴权

```python
@asynccontextmanager
async def lifespan(_: FastAPI)                      # 启动恢复 / 关闭停止

def is_authenticated(request: Request) -> bool
def require_auth(request: Request) -> None          # 401
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse
```

### 路由处理函数

```python
def auth_session(request: Request) -> dict[str, bool]
def auth_login(request: Request, payload: LoginPayload) -> dict[str, bool]
def auth_logout(request: Request) -> dict[str, bool]
def list_apps(_: None = Depends(require_auth)) -> dict[str, object]
def create_app(payload: CreateAppPayload, _: None = Depends(require_auth)) -> dict[str, object]
def app_detail(app_id: int, _: None = Depends(require_auth)) -> dict[str, object]
def delete_app(app_id: int, _: None = Depends(require_auth)) -> dict[str, bool]
def start_app(app_id: int, _: None = Depends(require_auth)) -> dict[str, object]
def stop_app(app_id: int, _: None = Depends(require_auth)) -> dict[str, object]
def restart_app(app_id: int, _: None = Depends(require_auth)) -> dict[str, object]
async def upload_script(app_id: int, file: UploadFile = File(...),
                        manual_dependencies: str = Form(""),
                        _: None = Depends(require_auth)) -> dict[str, object]
def download_script(app_id: int, _: None = Depends(require_auth)) -> Response
def app_logs(app_id: int, _: None = Depends(require_auth)) -> dict[str, str]
def get_settings(_: None = Depends(require_auth)) -> dict[str, object]
def update_settings(payload: SettingsPayload, _: None = Depends(require_auth)) -> dict[str, object]
def spa_entry(full_path: str) -> Response
```

### 内部辅助

```python
def app_payload(managed_app: ManagedApp) -> dict[str, object]
def settings_payload() -> dict[str, object]
def get_app_or_404(app_id: int) -> ManagedApp
def _process_uploaded_script(app_id: int, pending_path: Path, manual_dependencies: str) -> None
```

- `app_payload`：把 `ManagedApp` 转为 API JSON（含嵌套 `progress` 与 `dependencies`）。
- `settings_payload`：组装镜像预设、当前选择与生效 URL。
- `_process_uploaded_script`：后台线程主体；持 `manager.lock`；捕获 `SyntaxError` 与 `Exception`；`finally` 清理临时文件。

---

## 调用关系速查

```text
main.list_apps / app_detail
  └─ repo.list_apps / repo.get_app

main.create_app
  ├─ repo.create_app
  └─ manager.app_dir

main.upload_script
  └─ threading.Thread(_process_uploaded_script)
        ├─ repo.get_app / set_progress / set_status / update_upload
        ├─ manager.stop
        ├─ dependency_inference.infer_dependencies
        └─ manager.start
              ├─ manager.stop
              ├─ manager.install_dependencies
              │     ├─ dependency_inference.merge_dependencies
              │     ├─ repo.get_setting
              │     └─ pip_mirror.build_pip_index_args
              ├─ subprocess.Popen
              └─ manager._watch_process (thread)

main.start_app / restart_app → manager.start
main.stop_app              → manager.stop
main.delete_app            → manager.delete → manager.stop → rmtree → repo.delete_app
main.spa_entry             → FileResponse(FRONTEND_INDEX)
main.get_settings / update_settings → settings_payload / repo.get_setting / set_setting

lifespan 启动 → manager.restore_desired → repo.list_apps → manager.start(install=False)
lifespan 关闭 → manager.shutdown → manager.stop(desired=True)
```

---

## 状态写入点对照

| 位置 | 写入内容 |
| --- | --- |
| `create_app` 路由 | 仅插入记录（`status='new'`） |
| 上传线程 | `installing`、`error`、进度 25/35/45/70/90/100 |
| `ProcessManager.start` | `installing`/`starting`、`running` + pid、`desired_running=1` |
| `ProcessManager.stop` | `stopped`、pid=NULL、`desired_running` 依参数 |
| `ProcessManager.install_dependencies` | `error`、进度 `failed` |
| `ProcessManager._watch_process` | `error`（期望运行但异常退出）或 `stopped` |
| `settings_save` → `update_settings` | `app_settings` 两个键 |
