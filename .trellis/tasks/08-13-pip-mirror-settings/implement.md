# Implement — pip 镜像源系统设置

> 复杂任务，按顺序执行；每个步骤结尾给出验证命令。

## 实施清单（有序）

### S1 持久层：`AppRepository` 增 `app_settings` 表与读写
- 编辑 `app/database.py`：
  - 模块顶部新增常量 `PIPS_INDEX_SETTING_KEY = "pip_index_url"`、`PIPS_SELECTOR_SETTING_KEY = "pip_index_selector"`。
  - `init_schema()` 末尾追加 `CREATE TABLE IF NOT EXISTS app_settings(key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)`。
  - 新增方法 `get_setting(key, default="") -> str`、`set_setting(key, value)`，写入带 `INSERT ... ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP`。
- 验证：
  ```bash
  python -c "from app.database import AppRepository; import tempfile, pathlib; p=pathlib.Path(tempfile.mkdtemp())/'t.db'; r=AppRepository(p); r.set_setting('pip_index_url','https://x/simple'); assert r.get_setting('pip_index_url')=='https://x/simple'; assert r.get_setting('missing','d')=='d'; print('ok')"
  ```

### S2 镜像源常量与工具：新增 `app/pip_mirror.py`
- 新建文件 `app/pip_mirror.py`（内容见 design.md 契约）。
  - `PipMirrorPreset` dataclass、`PIP_MIRROR_PRESETS`（official/tsinghua/aliyun/tencent/ustc/custom）、`OFFICIAL_INDEX`。
  - `validate_mirror_url(url) -> (bool, str)`：必须 http(s)，必须含 netloc，允许 `https://.../simple` 与任意路径；custom 时空串非法。
  - `normalize_mirror_url(url)`：strip + 去尾斜杠。
  - `build_pip_index_args(url) -> list[str]`：`["-i", url]`，http 时 `+ ["--trusted-host", urlparse(url).netloc]`。
  - `selector_url(selector, custom_url)`：custom 返回 custom_url，其他在预设里查。
- 验证：
  ```bash
  python -c "from app.pip_mirror import *; print(validate_mirror_url('https://pypi.org/simple')); print(build_pip_index_args('http://mirrors.intra:8081/simple'))"
  ```

### S3 应用层：`install_dependencies` 应用镜像源
- 编辑 `app/process_manager.py` `install_dependencies`：
  - import `from app.pip_mirror import PIPS_INDEX_SETTING_KEY, build_pip_index_args`。
  - 在 `pip install` 命令构造前读取 `index_url = self.repo.get_setting(PIPS_INDEX_SETTING_KEY, "")`；非空则 `pip_cmd += build_pip_index_args(index_url)`。
- 验证：
  ```bash
  python tests/test_pip_mirror_install.py  # 新增，断言调用命令包含 -i
  # 或最小烟测：手写一段 fake repo 检查命令拼接
  ```

### S4 UI：新增 `/settings` 路由与模板
- 编辑 `app/main.py`：
  - import `from app.pip_mirror import PIP_MIRROR_PRESETS, OFFICIAL_INDEX, validate_mirror_url, normalize_mirror_url, selector_url`，以及 DB 常量。
  - 新增 `GET /settings`：渲染 `settings.html`，传入 `presets`、`current_selector`、`current_custom_url`、`error`。
  - 新增 `POST /settings`：处理 `source` + `custom_url`，custom 走校验失败重渲染带 422/原样回显；保存 `selector` + `url`；成功 `RedirectResponse("/settings", 303)`。
- 新建 `app/templates/settings.html`：复用 topbar + 一个 panel；radio 单选 `source` + 自定义 URL 输入；当前选中项通过模板 `checked`/`selected` 高亮；JS 切换自定义 URL 显示。
- 编辑 `app/templates/dashboard.html` 顶栏：在退出按钮旁加 `<a class="ghost" href="/settings">系统设置</a>`。
- 验证：
  ```bash
  uvicorn app.main:app --port 8765 &
  # 浏览器或 curl 检查 /settings GET 200、POST 保存后 303；未登录得到 303→/login。
  ```

### S5 样式微调（可选）
- 编辑 `app/static/styles.css`：若 `.topbar .ghost` 间距或 settings 页面单选布局不佳，补几条规则；优先复用现有类。
- 验证：浏览器目测。

### S6 测试补强
- 新增 `tests/test_pip_mirror.py`：
  - `validate_mirror_url` 正负用例（https/空/带端口 http/怪字符）。
  - `build_pip_index_args` http/https 输出对比。
- 在 `tests/` 或既有安装测试里加：mock `subprocess.run`，断言设置开启后命令含 `-i`，关闭后不含。
- 验证：
  ```bash
  pytest -q
  ruff check .
  ```

## 验证总命令（实施完成后一次性跑）

```bash
pytest -q
ruff check .
# 手测：
uvicorn app.main:app --port 8765
# - 登录后顶栏有「系统设置」；
# - GET /settings 显示六个预设；
# - 选清华源保存 → 重载仍选中清华；
# - 自定义 http://mirrors.intra:8081/simple 保存成功；
# - 自定义 "notaurl" 保存失败给出提示，不写库；
# - 在 /apps/{id} 上传带依赖的脚本观察 install.log 出现 `-i https://...`。
```

## 风险与回滚点

| 风险 | 触发 | 回滚 |
|---|---|---|
| `pip install` 拼接命令位置错误破坏原有依赖安装 | S3 改错 | git revert process_manager.py；DB 设置不影响旧代码 |
| 校验逻辑放宽导致非法 URL 写入 | S2/S4 校验不严 | 加 unit test 覆盖；admin 可手动选官方源重置 |
| 模板渲染 KeyError | S4 presets/selector 传参缺失 | 浏览器手测 GET /settings，看 stacktrace |
| ruff/pytest 失败 | S6 未跑或忽视 | 实施完成必须跑 `pytest -q` + `ruff check .` |

## Review Gates

1. PRD 验收：跑「验证总命令」逐条对照 AC1–AC7。
2. 代码质量：`ruff check .` clean，`pytest -q` 全绿。
3. 跨层贯通：保存 → DB → install_dependencies 命令包含 `-i`（AC3/AC5）。
4. 提交前自检 git diff，确认仅改动 5 个文件 + 1 新模板 + 1 新模块 + 1 新测试（不破坏静态/Docker 路径）。