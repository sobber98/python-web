# 05 · Web API 与 SPA 前端

后端路由集中在 [`app/main.py`](../../app/main.py)，前端是独立的 React SPA（[`frontend/`](../../frontend)）。FastAPI 只暴露 JSON API，并托管 Vite 构建产物与 SPA 入口，不再使用 Jinja2 模板。

## 1. 认证机制

- 使用 Starlette `SessionMiddleware`，`secret_key` 来自 `config.toml`（缺省则每次启动随机生成），`same_site="lax"`。
- 登录：`POST /api/auth/login`，JSON `{"password": "..."}`；优先与数据库 `app_settings.admin_password_hash`（PBKDF2）比对，未改密时回退到 `settings.admin_password`（`secrets.compare_digest`），成功写入 `request.session["authenticated"] = True`。
- 登出：`POST /api/auth/logout` 清空会话。
- 会话探测：`GET /api/auth/session` 返回 `{"authenticated": bool}`，供 SPA 判断是否跳转登录页。
- 除登录与会话探测外，所有 `/api/*` 路由都依赖 `require_auth`，未登录返回 `401 {"error": "请先登录后再操作。"}`。

前端 `api.ts` 在收到非登录接口的 401 时会执行 `window.location.replace('/login')`，避免停留在失效会话页面。

> 无 CSRF Token；会话依赖 Cookie，前后端同源部署。生产环境应置于可信网络/反向代理之后。

## 2. API 路由总表

| 方法 | 路径 | 鉴权 | 行为 |
| --- | --- | --- | --- |
| GET | `/api/auth/session` | 无 | `{"authenticated": bool}` |
| POST | `/api/auth/login` | 无 | 校验密码；失败 401 `{"error": "密码错误，请重试。"}` |
| POST | `/api/auth/logout` | 无 | 清空会话，`{"ok": true}` |
| GET | `/api/apps` | 需要 | `{"apps": [ManagedApp]}` |
| POST | `/api/apps` | 需要 | 创建应用；名称为空 400；成功 201 返回 `ManagedApp` |
| GET | `/api/apps/{app_id}` | 需要 | 应用详情；不存在 404 |
| DELETE | `/api/apps/{app_id}` | 需要 | 停止进程并删除目录与记录，`{"ok": true}` |
| POST | `/api/apps/{app_id}/start` | 需要 | `manager.start(id, install=True)`，返回最新 `ManagedApp` |
| POST | `/api/apps/{app_id}/stop` | 需要 | `manager.stop(id, desired=False)`，返回最新 `ManagedApp` |
| POST | `/api/apps/{app_id}/restart` | 需要 | `manager.restart(id)`，返回最新 `ManagedApp` |
| POST | `/api/apps/{app_id}/upload` | 需要 | 仅接受 `.py`；保存临时文件并启动后台线程；返回 `{"accepted": true, "app_id": id}` |
| GET | `/api/apps/{app_id}/download` | 需要 | `FileResponse(text/x-python)`；无脚本 404 |
| GET | `/api/apps/{app_id}/logs` | 需要 | `{"logs": "<tail>"}` |
| GET | `/api/settings` | 需要 | 镜像源预设、当前选择与生效 URL |
| PUT | `/api/settings` | 需要 | JSON `{"source", "custom_url"}`；校验失败 400；成功返回最新设置 |
| PUT | `/api/settings/password` | 需要 | JSON `{"current_password", "new_password"}`；当前密码错误/新密码不足 8 位/与原密码相同返回 400；成功返回 `{"ok": true}` |
| GET | `/{full_path:path}` | 无 | SPA 入口（见第 4 节） |

`ManagedApp` JSON 结构：

```json
{
  "id": 1,
  "name": "演示应用",
  "slug": "demo",
  "script_name": "main.py",
  "status": "installing",
  "desired_running": true,
  "pid": null,
  "last_error": "",
  "progress": {
    "stage": "installing",
    "percent": 70,
    "message": "正在安装依赖..."
  },
  "dependencies": {
    "inferred": ["requests", "beautifulsoup4"],
    "manual": ["requests==2.32.3"]
  },
  "created_at": "2026-01-01 00:00:00",
  "updated_at": "2026-01-01 00:00:00"
}
```

状态内部值保持不变：`new`、`installing`、`starting`、`running`、`stopped`、`error`，中文映射只发生在前端展示层。

## 3. 上传与进度

`POST /api/apps/{id}/upload` 接收 `multipart/form-data`：

- `file`：必须为 `.py`。
- `manual_dependencies`：文本，每行一个依赖。

接口在写临时文件并设置 `progress=25` 后立即返回，真正的处理由后台线程 `_process_uploaded_script` 完成：

```text
停止旧进程 → status=installing → AST 推断依赖 → 覆盖 main.py
→ 写库 → manager.start(install=True) → venv / pip install / Popen
```

前端用 `XMLHttpRequest` 读取 `xhr.upload.onprogress` 展示**上传进度**；随后轮询 `GET /api/apps/{id}` 读取 `progress.percent/message` 展示**安装进度**。两者在 UI 上分开呈现。

## 4. SPA 托管

- `app.mount("/static", StaticFiles(directory=APP_DIR / "static"))`。
- Vite 构建配置 `base: '/static/app/'`，产物写入 `app/static/app/`（Docker 中由 Node 构建阶段复制）。
- 兜底路由：

```python
@app.get("/{full_path:path}", include_in_schema=False)
def spa_entry(full_path: str) -> Response:
    if full_path.startswith(("api/", "static/")):
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(FRONTEND_INDEX)
```

因此 `/`、`/login`、`/apps/1`、`/settings` 都返回同一份 `index.html`，由 React Router 接管客户端路由。若构建产物缺失，返回 503 HTML 并提示运行 `npm run build`。

## 5. 前端工程结构

```text
frontend/
├── index.html
├── vite.config.ts          # base、构建输出目录、/api 开发代理
├── vitest.config.ts        # jsdom + Testing Library
├── tailwind.config.cjs
├── package.json
└── src/
    ├── main.tsx            # React 挂载点
    ├── App.tsx             # QueryClient、BrowserRouter、路由表
    ├── index.css           # Tailwind 入口与基础样式
    ├── types.ts            # API 类型
    ├── lib/
    │   ├── api.ts          # 类型化 fetch 客户端与 ApiError
    │   ├── queries.ts      # TanStack Query hooks、轮询、上传 XHR
    │   └── format.ts       # 状态/阶段中文映射、时间格式化
    ├── components/
    │   ├── AppLayout.tsx   # 顶栏、导航、退出登录
    │   ├── ProtectedRoute.tsx
    │   ├── Logo.tsx
    │   ├── apps/           # 应用侧栏、上传、控制、日志
    │   └── ui/             # Button、Card、Field、Badge、Progress、Dialog
    ├── pages/
    │   ├── LoginPage.tsx
    │   ├── DashboardPage.tsx
    │   └── SettingsPage.tsx
    └── test/               # Vitest 页面渲染测试
```

### 路由

| 路径 | 页面 | 说明 |
| --- | --- | --- |
| `/login` | `LoginPage` | 已登录时自动跳回来源页或 `/` |
| `/` | `DashboardPage` | 有应用时自动重定向到第一个应用 |
| `/apps/:appId` | `DashboardPage` | 选中应用详情 |
| `/settings` | `SettingsPage` | pip 镜像源设置 |
| `*` | — | 重定向 `/` |

`ProtectedRoute` 通过 `useSession()` 判断登录状态：加载中显示全屏 loader，未登录 `<Navigate to="/login" />`。

### 服务端状态与轮询

| 数据 | Query key | 刷新方式 |
| --- | --- | --- |
| 会话 | `['session']` | 加载时一次，`staleTime=30s` |
| 应用列表 | `['apps']` | 每 4 秒轮询 |
| 应用详情 | `['apps', id]` | 每 2.5 秒轮询 |
| 日志 | `['apps', id, 'logs']` | 每 4 秒轮询 + 手动刷新 |
| 镜像设置 | `['settings']` | 保存成功后写入缓存 |

创建、启动、停止、重启、删除成功后都会失效相关 query，立即刷新侧栏与详情。

### Settings 交互

1. 预设列表来自 `GET /api/settings` 的 `presets`。
2. 选择“自定义”时显示 URL 输入框。
3. 保存调用 `PUT /api/settings`：
   - `source == "custom"`：`validate_mirror_url` 失败 → 400，前端展示中文错误，不写库。
   - 未知预设 key → 400 `"未知的镜像源选项。"`。
   - 成功写 `pip_index_selector` 与 `pip_index_url`。
4. 页面展示当前生效 URL，未设置时提示回退 PyPI 官方源。

## 6. 错误响应一览

| 场景 | 状态码 | 形式 |
| --- | --- | --- |
| API 未登录 | 401 | `{"error": "请先登录后再操作。"}` |
| 登录密码错误 | 401 | `{"error": "密码错误，请重试。"}` |
| 应用不存在 | 404 | `{"error": "应用不存在。"}` |
| 应用名为空 | 400 | `{"error": "应用名称不能为空。"}` |
| 非 `.py` 上传 | 400 | `{"error": "仅支持上传 .py 文件。"}` |
| 无脚本可下载 | 404 | `{"error": "当前应用尚未上传脚本。"}` |
| 请求体校验失败 | 422 | `{"error": "请求参数不合法，请检查后重试。"}` |
| 未知 API / 静态路径 | 404 | `{"error": "Not found"}` |
| 前端未构建 | 503 | HTML 提示构建命令 |
