# Python Management Platform · Code Wiki

面向开发者的项目代码文档。本 Wiki 基于仓库当前 `master` 分支代码生成，覆盖架构、模块、数据模型、运行机制、HTTP 接口、配置部署与测试。

> 一句话概括：一个基于 FastAPI 的**单管理员** Web 控制台，用于上传多个 Python 脚本，并为每个脚本创建独立虚拟环境、安装依赖、以子进程方式常驻运行，同时提供日志、状态轮询与启动恢复能力。

---

## 目录

| 章节 | 内容 |
| --- | --- |
| [01 架构总览](01-architecture.md) | 技术栈、运行时结构、分层、请求/进程数据流、设计取舍 |
| [02 模块职责](02-modules.md) | 每个源码文件的职责、对外接口与协作关系 |
| [03 数据模型](03-data-model.md) | SQLite 表结构、`ManagedApp` 字段、Repository 全部方法 |
| [04 应用生命周期](04-process-lifecycle.md) | 上传流水线、状态机、进程启动/停止/恢复、日志 |
| [05 Web 接口与前端](05-web-api.md) | 路由表、认证与错误处理、模板与前端轮询机制 |
| [06 依赖推断与 pip 镜像](06-dependencies-and-mirror.md) | AST 依赖推断、手动依赖合并、镜像源配置链路 |
| [07 配置、运行与部署](07-configuration-deployment.md) | `config.toml`、本地运行、Docker/Compose、CI、测试 |
| [08 关键类与函数索引](08-api-reference.md) | 按模块整理的类/函数签名速查表 |

---

## 项目速览

| 项目属性 | 值 |
| --- | --- |
| 项目名 | `python-management-platform`（`pyproject.toml`） |
| 版本 | `0.1.0` |
| Python 要求 | `>=3.11`（代码使用 `tomllib`、`sys.stdlib_module_names`） |
| Web 框架 | FastAPI + Starlette（JSON API、SessionMiddleware） |
| 持久化 | SQLite（标准库 `sqlite3`，无 ORM） |
| 进程模型 | 每个应用一个 `.venv` + 一个 `subprocess.Popen` 子进程（独立进程组） |
| 默认端口 | 容器内 `7999`（`Dockerfile` 的 uvicorn 参数） |
| 前端 | React 18 + TypeScript + Vite + Tailwind CSS + React Router + TanStack Query（独立 SPA） |
| 测试 | 后端 pytest + FastAPI `TestClient`；前端 Vitest + Testing Library |

## 仓库结构

```text
.
├── app/                        # 后端源码（唯一 Python 包）
│   ├── __init__.py
│   ├── config.py               # 读取 config.toml → Settings
│   ├── database.py             # SQLite 仓库层 + schema/迁移
│   ├── models.py               # ManagedApp 数据模型
│   ├── dependency_inference.py # AST 依赖推断与依赖合并
│   ├── pip_mirror.py           # pip 镜像源预设、校验、参数拼装
│   ├── process_manager.py      # venv / pip / 子进程 / 日志 / 恢复
│   ├── main.py                 # FastAPI 应用、JSON API、SPA 托管、上传编排
│   └── static/app/             # Vite 构建产物（生成目录，不入库）
├── frontend/                   # React + TypeScript SPA
│   ├── src/pages/              # Login / Dashboard / Settings
│   ├── src/components/         # 布局、应用卡片与通用 UI
│   ├── src/lib/                # API 客户端、Query hooks、格式化
│   └── src/test/               # Vitest 页面渲染测试
├── tests/                      # 后端 pytest 测试
├── .github/workflows/ci.yml    # 测试 + 构建 + 推送 GHCR 镜像
├── Dockerfile                  # Node 构建阶段 + python:3.13-slim 运行阶段
├── docker-compose.prod.yml     # 生产编排（host 网络 + 命名卷）
├── config.example.toml         # 配置模板
├── pyproject.toml              # 依赖与 pytest 配置
└── AGENTS.md / .trellis/       # Trellis 开发规范与任务工作流（非运行时）
```

## 30 秒了解核心链路

```text
浏览器登录（密码 = config.toml 的 admin_password）
        │
        ▼
创建应用 → 上传 .py（存为 data/apps/<slug>/main.py）
        │
        ├─ 后台线程：AST 推断依赖 → 写库
        ├─ 创建/复用 data/apps/<slug>/.venv
        ├─ pip install 推断依赖 + 手动依赖（可指定镜像源）
        └─ Popen 启动脚本，stdout/stderr → runtime.log
        │
        ▼
前端 SPA 每 4 秒轮询 `/api/apps` 与 `/api/apps/{id}`，刷新状态、进度条和日志；浏览器上传进度由 XHR `upload.onprogress` 实时提供。
```

完整细节见 [04 应用生命周期](04-process-lifecycle.md)。

## 阅读建议

- **第一次接触项目**：按 01 → 02 → 04 → 05 顺序阅读。
- **要改数据库或字段**：先读 [03 数据模型](03-data-model.md)，注意 `_ensure_column` 的轻量迁移约定。
- **要排查启动/停止问题**：直接看 [04 应用生命周期](04-process-lifecycle.md) 的“进程控制”与“启动恢复”小节。
- **要部署**：看 [07 配置、运行与部署](07-configuration-deployment.md)。
- **要查函数签名**：看 [08 关键类与函数索引](08-api-reference.md)。

## 已知边界（重要）

- 仅有一个管理员密码，无用户体系、无 CSRF Token、无 HTTPS 终止逻辑，依赖反向代理与可信网络。
- 上传的代码**没有沙箱隔离**，以服务进程同一用户身份运行；README 明确说明仅面向“可信管理员上传的代码”。
- 虚拟环境路径固定为 `.venv/bin/python`，因此运行时假定为 POSIX 环境（Linux/macOS/Docker），不支持 Windows。
- 上传处理使用进程内后台线程，非任务队列；进程重启会中断进行中的安装（但已标记 `desired_running` 的应用会在启动时恢复）。
