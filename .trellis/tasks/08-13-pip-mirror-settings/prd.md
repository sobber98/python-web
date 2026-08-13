# 系统设置：pip 镜像源配置

## Goal

在 Web 平台管理后台新增「系统设置」入口，让可信管理员能够在 UI 中配置 pip 安装依赖时使用的镜像源（官方源 + 国内常用加速源 + 自定义 URL），配置后由 `ProcessManager.install_dependencies` 应用，使后续上传/重启应用时走选定的镜像源。

解决：国内服务器拉 PyPI 官方源时 `setuptools`/`flask` 构建依赖下载失败、依赖安装超时的问题。

## Background / 已知事实（来自代码勘察）

- FastAPI 单 `app/main.py`，路由全部内联；模板 `app/templates/dashboard.html` 顶栏（`.topbar`）目前只有标题与退出登录按钮。
- 配置加载在 `app/config.py`：`Settings` 为 `frozen=True` dataclass，启动时一次性读 `config.toml`，运行期只读、无法承载用户改动。`admin_password`/`secret_key`/`db_path`/`data_dir` 都来自此处。
- 依赖安装在 `app/process_manager.py:162-191` `install_dependencies()`，调用：
  `subprocess.run([str(venv_python), "-m", "pip", "install", *dependencies], ...)`
  当前不传任何镜像参数。
- 持久化在 `app/database.py`：`AppRepository` 用 SQLite，表 `managed_apps`，`init_schema()` 已有 `_ensure_column` 兼容迁移风格。无独立「设置」表。
- 现有鉴权：`require_page_auth` / `require_auth`，会话中间件校验管理员登录。
- 静态资源 `app/static/styles.css`，模板用纯原生 JS + `<form>` 提交，风格统一为「服务端渲染 + 偶发 fetch 轮询」。
- README/Docker 部署：`ghcr.io/sobber98/python-management-platform`。

## Requirements

### 功能性
- R1 顶栏新增「系统设置」按钮，点击进入 `/settings` 页面。
- R2 `/settings` 页面展示当前生效的镜像源，并提供单选选项：
  - 官方源（PyPI）：`https://pypi.org/simple`
  - 国内常用加速源（内置预设，至少含清华、阿里云、腾讯云、中科大）
  - 自定义：用户填入 URL
- R3 提交后写入持久化存储，并应用到 `install_dependencies`：在 `pip install` 命令后追加 `-i <url>`（必要时含 `--trusted-host`）。
- R4 配置立即生效，无需重启服务（沿用现有 `ProcessManager` 单例）。
- R5 在 `/settings` 页面对自定义 URL 做基本格式校验（必须为 http(s) 且结尾为 `/simple` 或合法 index path；失败给出错误提示）。
- R6 不影响 `config.toml` 中静态配置；镜像源属于运行时可变数据库设置。

### 非功能性 / 约束
- N1 仅管理员可访问 `/settings`（沿用 `require_page_auth`）。
- N2 不引入新前端框架；保持原生 + 现有模板结构。
- N3 镜像源预设列表在代码中常量化，便于后续扩展。
- N4 兼容现有 Docker 部署路径（数据库随 `data_dir` 持久化，无需改 compose）。
- N5 保留向后兼容：未配置时回退到官方 PyPI 源，行为与现状一致。

## Acceptance Criteria

- [ ] AC1 顶栏出现「系统设置」按钮，点击跳转到 `/settings`，未登录时被重定向到 `/login`。
- [ ] AC2 `/settings` 显示当前生效源；可选预设含官方、清华、阿里云、腾讯云、中科大，以及「自定义」。
- [ ] AC3 选择预设或填自定义 URL 并保存后，刷新 `/settings` 仍显示该选择，且 `install_dependencies` 生成的 pip 命令包含 `-i <url>`。
- [ ] AC4 自定义 URL 非法（非 http(s)、空、明显错误）时保存失败并提示，不写入持久层。
- [ ] AC5 未配置镜像源时 `pip install` 命令与改动前完全一致（不加 `-i`）。
- [ ] AC6 服务重启后配置仍生效（来自持久化层）。
- [ ] AC7 现有上传/启动/停止/重启/删除流程行为不变，仅依赖安装命令受镜像源影响。

## Out of Scope

- 镜像源连通性探测 / 测速。
- 每个应用独立的镜像源（本期为全局设置）。
- `pip.conf` 全局文件生成（本期仅在平台调用 pip 时传 `-i`）。
- 修改 `config.toml` 或将设置写入 `config.toml`。
- 其它 pip 参数（`--extra-index-url`、代理、超时）。

## Open Questions

无（所有产品决策已澄清）。

## Resolved Decisions

- Q1 持久化形态：采用 SQLite 新增 `app_settings(key TEXT PRIMARY KEY, value TEXT)` 表，由 `AppRepository` 提供 `get_setting`/`set_setting`，`init_schema` 同步建表。理由：与现有 repo 风格一致、事务统一、跟随 `db_path` 持久化，Docker 路径无需改动。
- Q2 是否加入「测试连接」按钮：本期不做，列入 Out of Scope。
- Q3 自定义 http 源：后端在生成 pip 命令时检测 URL scheme，`http` 自动追加 `--trusted-host <host>`（从 URL 解析主机名，含端口则一并写入），`https` 不追加。理由：兼容内网 http 镜像（devpi 等），管理员可控。
- Q4 入口形态：顶栏新增纯文字「系统设置」ghost 风格按钮，与「退出登录」并排；点击跳转独立 `/settings` 页面，原生 form 提交、服务端渲染校验。理由：与现有架构一致，零新增前端依赖。

## Notes

- 持久层倾向：在 `AppRepository` 中新增 `get_setting(key, default)` / `set_setting(key, value)` + `init_schema` 加 `app_settings` 表。
- 应用层倾向：`ProcessManager` 增加 `self.pip_index_url` 依据（运行时从 repo 查询或注入回调），或直接让 `install_dependencies` 末尾调用 `repo.get_setting("pip_index_url", "")` 决定是否追加参数。后者更解耦，符合「立即生效」。
- 前端倾向：新增 `templates/settings.html` + 路由 `GET/POST /settings`，复用顶栏。