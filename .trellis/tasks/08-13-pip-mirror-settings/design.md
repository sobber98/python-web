# Design — pip 镜像源系统设置

## 架构与边界

新增三个改动点，保持现有「FastAPI 路由内联 + SQLite repo + 服务端渲染模板」架构，零新增依赖：

1. **持久层**：`AppRepository` 新增 `app_settings` 表与 K/V 读写方法。
2. **应用层**：`ProcessManager.install_dependencies` 在生成 pip 命令前从 repo 读取设置，按需追加 `-i` / `--trusted-host`。
3. **表现层**：新增 `/settings` 路由（GET 渲染 + POST 保存）、`templates/settings.html`、`dashboard.html` 顶栏按钮、共享顶栏 CSS。

## 数据流

```
管理员 → POST /settings (form: source + custom_url)
   ↓ 校验（PIPMirrorPresets 枚举 or 合法 URL）
AppRepository.set_setting("pip_index_url", url)
AppRepository.set_setting("pip_index_selector", "official|tsinghua|aliyun|tencent|ustc|custom")
   ↓
ProcessManager.install_dependencies()
   ↓ read_pip_index_args() → repo.get_setting("pip_index_url", "")
   ↓ 若非空 → 追加 ["-i", url] + (http ? ["--trusted-host", host] : [])
subprocess.run([venv_python, "-m", "pip", "install", *deps, *mirror_args])
```

## 契约

### `app/database.py` 新增

```python
PIPS_INDEX_SETTING_KEY = "pip_index_url"
PIPS_SELECTOR_SETTING_KEY = "pip_index_selector"

def init_schema(self):
    # 既有 managed_apps …
    conn.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

def get_setting(self, key: str, default: str = "") -> str
def set_setting(self, key: str, value: str) -> None
```

`set_setting` 使用 `INSERT … ON CONFLICT(key) DO UPDATE`（SQLite 3.24+），保证一次往返。

### `app/pip_mirror.py`（新模块，集中常量 + 校验）

```python
@dataclass(frozen=True)
class PipMirrorPreset:
    key: str        # official / tsinghua / aliyun / tencent / ustc / custom
    label: str      # 中文展示
    url: str        # 实际 -i 值，custom 时为空（用户填）

PIP_MIRROR_PRESETS: list[PipMirrorPreset] = [...]

OFFICIAL_INDEX = "https://pypi.org/simple"

def normalize_mirror_url(url: str) -> str  # strip、去尾斜杠
def validate_mirror_url(url: str) -> tuple[bool, str]
    # 必须 http(s) 且包含 netloc；非空；末尾不强求 /simple（宽松，兼容 devpi 风格）
def build_pip_index_args(url: str) -> list[str]
    # ["-i", url] + (http → ["--trusted-host", urlparse(url).hostname or netloc])
def selector_url(preset_key: str, custom_url: str) -> str
    # 解析预设 key → url；custom → custom_url
```

### `app/process_manager.py` 修改 `install_dependencies`

```python
from app.pip_mirror import PIPS_INDEX_SETTING_KEY, build_pip_index_args

def install_dependencies(self, app, progress=None) -> bool:
    ...
    index_url = self.repo.get_setting(PIPS_INDEX_SETTING_KEY, "")
    pip_cmd = [str(venv_python), "-m", "pip", "install", *dependencies]
    if index_url:
        pip_cmd += build_pip_index_args(index_url)
    subprocess.run(pip_cmd, check=True, stdout=log, stderr=subprocess.STDOUT)
```

### `app/main.py` 新增路由

```python
@app.get("/settings", response_class=HTMLResponse)
def settings_page(request, _=Depends(require_page_auth)):
    selector = repo.get_setting(PIPS_SELECTOR_SETTING_KEY, "official")
    custom_url = repo.get_setting(...) if selector == "custom" else ""
    error = ""
    return templates.TemplateResponse(request, "settings.html", {
        "presets": PIP_MIRROR_PRESETS,
        "current_selector": selector,
        "current_custom_url": custom_url,
        "official_url": OFFICIAL_INDEX,
        "error": error,
    })

@app.post("/settings")
def settings_save(request, source: str = Form(...), custom_url: str = Form("")):
    require_page_auth(request)
    if source == "custom":
        ok, msg = validate_mirror_url(custom_url)
        if not ok: 重新渲染 settings.html with error
        url = normalize_mirror_url(custom_url)
    elif source in PRESET_KEYS:
        url = preset.url
    else:
        error
    repo.set_setting(PIPS_SELECTOR_SETTING_KEY, source)
    repo.set_setting(PIPS_INDEX_SETTING_KEY, url)
    return RedirectResponse("/settings", status_code=303)
```

### `app/templates/dashboard.html` 修改顶栏

在「退出登录」按钮旁加：
```html
<a class="ghost" href="/settings">系统设置</a>
<form method="post" action="/logout">…</form>
```

### 新增 `app/templates/settings.html`

复用 dashboard 的 `.topbar` + `.layout` 结构，左侧 `/` 链接回首页，主区单列 panel：
- 隐藏 `<input type="hidden" name="source" value="...">` 切换源；UI 用单选 radio：`name="source"`。
- 当 `source == "custom"` 时显示 `<input type="url" name="custom_url">`，JS `onchange` 切换可见性。
- 提交按钮「保存」。
- 错误信息用现有 `.error` 样式。

CSS 仅复用现有类（`.topbar`, `.ghost`, `.panel`, `.eyebrow`, `.stack`, `.error`, `.muted`, `.button-row`），必要时在 `app/static/styles.css` 末尾追加一两条规则。

## 兼容性与迁移

- 启动时旧 DB 没有 `app_settings` 表，`init_schema()` 用 `CREATE TABLE IF NOT EXISTS` 安全创建，无需手迁移脚本。
- 旧设置不存在 → `get_setting` 返回默认 `""` → `build_pip_index_args` 不被调用 → pip 命令与改动前完全一致（AC5）。
- `config.toml` 不动；管理员密码等设置仍只走 `config.toml`。

## Trade-offs

| 选择 | 利 | 弊 | 取舍 |
|---|---|---|---|
| 集中 `pip_mirror.py` 模块 | 单元测试可独立、复用 | 多一个文件 | ✅ |
| 每次 `install_dependencies` 主动读 DB | 立即生效、无需重启 | 每次多一次 SQLite 查询（<1ms） | ✅ 接受 |
| 单独 selector + url 两键 | UI 可回显选中预设，自定义 URL 独立保留 | 两个字段需保持一致 | ✅ 校验在保存端保证 |
| http 自动 `--trusted-host` | 兼容内网 http 镜像 | 略放宽 | ✅ 管理员可控 |

## 操作 / 回滚

- 回滚只需还原 4 个文件 + 删除 `pip_mirror.py` + `templates/settings.html`；DB 中 `app_settings` 留无副作用（旧代码不读）。
- 若误配 http 源导致 pip 失败，可在 `/settings` 选「官方源」保存，立即回归 PyPI，无需重启。