# 07 · 配置、运行与部署

## 1. 配置文件 `config.toml`

配置由 [`app/config.py`](../../app/config.py) 在**导入 `app.main` 时**读取，路径固定为当前工作目录下的 `config.toml`。

| 键 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `admin_password` | 是 | — | 管理员登录密码；为空则启动失败 |
| `secret_key` | 否 | 随机 `secrets.token_urlsafe(32)` | 会话签名密钥；不配置则每次重启使旧会话失效 |
| `data_dir` | 否 | `data` | 运行时数据根目录（相对路径按 cwd 解析后 `resolve()`） |
| `db_path` | 否 | `<data_dir>/manager.db` | SQLite 文件路径 |

模板见 [`config.example.toml`](../../config.example.toml)：

```toml
admin_password = "change-me"
secret_key = "replace-with-a-long-random-string"
data_dir = "data"
# db_path = "data/manager.db"
```

启动时会做的校验：

1. 文件不存在 → `RuntimeError: Configuration file not found: ...`。
2. `admin_password` 为空 → `RuntimeError: admin_password must be set ...`。

`sqlite3` 是标准库，无需额外依赖；`data_dir` 及其父目录由 `AppRepository` / `ProcessManager` 自动创建。

## 2. 本地运行

```bash
python -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate（但项目仅支持 POSIX 运行）
pip install -e ".[dev]"
cp config.example.toml config.toml
# 编辑 config.toml，设置 admin_password（生产环境同时设置 secret_key）

cd frontend
npm install
npm run build                 # 产物写入 ../app/static/app
cd ..

uvicorn app.main:app --reload --port 7999
```

前端热更新模式：

```bash
# 终端 1：后端
uvicorn app.main:app --reload --port 7999

# 终端 2：Vite 开发服务器，/api 代理到 7999
cd frontend
npm run dev                   # http://127.0.0.1:5173
```

要点：

- 必须在**仓库根目录**启动，否则找不到 `config.toml`。
- 未执行 `npm run build` 时，访问页面会返回 503 并提示构建命令。
- 运行期目录结构：

```text
<data_dir>/
├── manager.db
└── apps/
    └── <slug>/
        ├── main.py
        ├── .venv/
        ├── install.log
        └── runtime.log
```

前置条件：目标机器需要能创建 venv（Debian 系需 `python3-venv`），且 pip 可访问所选镜像源。

## 3. Docker

[`Dockerfile`](../../Dockerfile) 摘要：

| 阶段/指令 | 内容 |
| --- | --- |
| 前端构建阶段 | `node:20-slim`，`npm ci` + `npm run build`（`BUILD_OUT_DIR=dist`） |
| 基础镜像 | `python:3.13-slim` |
| 环境变量 | `PYTHONDONTWRITEBYTECODE=1`、`PYTHONUNBUFFERED=1`、`PIP_NO_CACHE_DIR=1`、`PYTHONPATH=/app` |
| 系统依赖 | `apt-get install python3-venv`（运行期建 venv 必需） |
| 工作目录 | `/app` |
| 安装 | `pip install --upgrade pip && pip install .`（非 editable）；复制前端产物到 `/app/app/static/app` |
| 运行用户 | `manager`（`useradd --create-home`，`/app` chown 给该用户） |
| 端口 | `EXPOSE 7999` |
| 启动 | `uvicorn app.main:app --host 0.0.0.0 --port 7999` |

构建与运行：

```bash
docker build -t python-management-platform:local .

cp config.example.toml config.toml
# 编辑 config.toml（admin_password、secret_key）

docker run --rm \
  -p 7999:7999 \
  -v "$(pwd)/config.toml:/app/config.toml:ro" \
  -v python-manager-data:/app/data \
  python-management-platform:local
```

注意事项：

- 配置文件以只读方式挂载；`data_dir` 必须落在 `/app/data`（命名卷），否则容器删除后脚本、venv、数据库全部丢失。
- 容器内以非 root 用户运行，挂载目录需可写。
- 子进程运行在同一容器内，但**不是安全沙箱**（README 明确说明）。

## 4. 生产 Compose

[`docker-compose.prod.yml`](../../docker-compose.prod.yml)：

```yaml
services:
  python-manager:
    image: ghcr.io/sobber98/python-management-platform:latest
    restart: unless-stopped
    stop_grace_period: 60s
    network_mode: host
    volumes:
      - ./config.toml:/app/config.toml:ro
      - python-manager-data:/app/data

volumes:
  python-manager-data:
```

| 配置 | 含义 |
| --- | --- |
| `restart: unless-stopped` | 崩溃或宿主重启后自动拉起；应用恢复依赖 `lifespan` 的 `restore_desired()` |
| `stop_grace_period: 60s` | 给 `SIGTERM` + 子进程清理留足时间（代码内部两次 5s 等待） |
| `network_mode: host` | 直接使用宿主网络栈，端口即 7999，无需 `ports` 映射 |
| 命名卷 | 持久化 `manager.db`、脚本、venv、日志 |

部署：

```bash
cp config.example.toml config.toml
# 设置强密码与 secret_key
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml down
```

升级流程（推荐）：`pull` → `up -d`；正在运行的应用会被停止并自动恢复（`desired_running=1`），依赖不会重装。

## 5. CI（GitHub Actions）

[`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) 在 `push` 到 `master`/`main` 以及所有 `pull_request` 时触发：

1. Checkout。
2. 安装 Python 3.13。
3. `python -m pip install -e '.[dev]'`。
4. `python -m pytest`。
5. `python -m compileall app tests`（语法级检查）。
6. `docker build`，打两个标签：`ghcr.io/<owner>/python-management-platform:<sha>` 与 `:latest`。
7. 仅 `push` 事件：登录 GHCR 并推送上述两个镜像。

因此：合并到主分支即发布 `latest` 镜像；PR 只构建不推送。

## 6. 测试

```bash
pip install -e '.[dev]'
python -m pytest
```

`pyproject.toml` 已设置 `testpaths = ["tests"]`、`pythonpath = ["."]`。

| 文件 | 关注点 |
| --- | --- |
| `tests/test_config.py` | 配置文件缺失、缺少密码、路径解析、`secret_key` |
| `tests/test_database.py` | slug 回退与唯一性、progress 默认值与截断、旧库自动迁移 |
| `tests/test_dependency_inference.py` | import 解析、标准库/本地模块过滤、手动依赖解析、合并去重与版本覆盖 |
| `tests/test_pip_mirror.py` | 设置项读写、URL 校验、pip 参数与 `--trusted-host` |
| `tests/test_pages.py` | 登录页渲染、dashboard 进度 UI、状态 API 鉴权与字段 |
| `tests/test_settings.py` | 设置页鉴权/渲染/保存/非法 URL、pip 命令注入点（mock `subprocess.run`） |
| `tests/test_process_manager.py` | 服务重启后按数据库 pid 停止遗留进程、`shutdown` 保留期望状态 |

测试对 `app.main` 采用 `monkeypatch.chdir(tmp_path)` + `importlib.reload(app.main)`，因为模块导入时就读取 `config.toml` 并创建全局单例。

## 7. 运维排查

| 现象 | 排查方向 |
| --- | --- |
| 启动报 `Configuration file not found` | 确认 cwd 下有 `config.toml`；容器中确认 `/app/config.toml` 挂载成功 |
| 上传后一直“安装中” | 查看 `install.log`；检查镜像源连通性、venv 创建权限 |
| 状态 `error` 且 `last_error` 含 `Dependency install failed` | 手动依赖拼写/版本不存在，或网络无法访问镜像源 |
| 状态 `error` 且 `Python syntax error` | 上传文件本身语法错误；原 `main.py` 未被覆盖 |
| 状态 `error` 且 `Process exited with code N` | 脚本运行崩溃，查看 `runtime.log` |
| 服务重启后应用未恢复 | 检查该应用 `desired_running` 是否为 1（手动停止会置 0） |
| 停止失败/超时 | 查看是否有 `Permission denied`/`Timed out stopping process group`；检查进程权限 |
| 登录后立即失效 | 未配置 `secret_key`，每次重启密钥变化 |
| 磁盘占用增长 | 日志不轮转；venv 每应用一份；按需清理 `data/apps/<slug>/` |

## 8. 备份与迁移

需要备份的只有 `<data_dir>`：

- `manager.db`（元数据与设置）
- `apps/<slug>/main.py`（脚本源码）
- 可选：`apps/<slug>/.venv/`（体积大，可在新机器重建，重建后需触发一次启动/上传）

迁移步骤：停止服务 → 复制 `data` 目录 → 恢复 `config.toml` → 启动。由于 venv 内含绝对路径，跨路径迁移后建议删除各应用 `.venv` 再启动（会重新创建并安装依赖）。

## 9. 环境与版本约束

| 项 | 约束 |
| --- | --- |
| Python | `>=3.11`（`tomllib`、`sys.stdlib_module_names`） |
| 镜像 | Python 3.13-slim |
| 平台 | Linux/macOS（依赖 `.venv/bin/python`、`os.killpg`、`start_new_session`） |
| 依赖 | `fastapi`、`uvicorn[standard]`、`itsdangerous`、`python-multipart`；开发额外 `pytest`、`httpx2`；前端 Node 20 + npm |
| 构建 | 前端 `npm run build`（Vite → `app/static/app`）；Docker 多阶段自动构建 |
