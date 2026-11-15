from __future__ import annotations

import secrets
import shutil
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from app.config import load_settings
from app.database import AppRepository, PIP_INDEX_URL_SETTING_KEY, PIP_INDEX_SELECTOR_SETTING_KEY
from app.dependency_inference import infer_dependencies
from app.models import ManagedApp
from app.pip_mirror import (
    OFFICIAL_INDEX,
    PIP_MIRROR_PRESETS,
    get_preset,
    normalize_mirror_url,
    selector_url,
    validate_mirror_url,
)
from app.process_manager import ProcessManager

settings = load_settings()
repo = AppRepository(settings.db_path)
manager = ProcessManager(repo, settings.data_dir)
APP_DIR = Path(__file__).resolve().parent
FRONTEND_INDEX = APP_DIR / "static" / "app" / "index.html"


@asynccontextmanager
async def lifespan(_: FastAPI):
    manager.restore_desired()
    try:
        yield
    finally:
        manager.shutdown()


app = FastAPI(title="Python Management Platform", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, same_site="lax")
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")


class LoginPayload(BaseModel):
    password: str


class CreateAppPayload(BaseModel):
    name: str


class SettingsPayload(BaseModel):
    source: str
    custom_url: str = ""


def is_authenticated(request: Request) -> bool:
    return bool(request.session.get("authenticated"))


def require_auth(request: Request) -> None:
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Authentication required")


def app_payload(managed_app: ManagedApp) -> dict[str, object]:
    return {
        "id": managed_app.id,
        "name": managed_app.name,
        "slug": managed_app.slug,
        "script_name": managed_app.script_name,
        "status": managed_app.status,
        "desired_running": managed_app.desired_running,
        "pid": managed_app.pid,
        "last_error": managed_app.last_error,
        "progress": {
            "stage": managed_app.progress_stage,
            "percent": managed_app.progress_percent,
            "message": managed_app.progress_message,
        },
        "dependencies": {
            "inferred": managed_app.inferred_list,
            "manual": managed_app.manual_list,
        },
        "created_at": managed_app.created_at,
        "updated_at": managed_app.updated_at,
    }


def settings_payload() -> dict[str, object]:
    selector = repo.get_setting(PIP_INDEX_SELECTOR_SETTING_KEY, "official")
    custom_url = repo.get_setting(PIP_INDEX_URL_SETTING_KEY, "") if selector == "custom" else ""
    preset = get_preset(selector)
    if preset and selector != "custom":
        effective_url = preset.url
    elif selector == "custom":
        effective_url = custom_url
    else:
        effective_url = OFFICIAL_INDEX
    return {
        "presets": [
            {"key": item.key, "label": item.label, "url": item.url}
            for item in PIP_MIRROR_PRESETS
        ],
        "selector": selector,
        "custom_url": custom_url,
        "effective_url": effective_url,
    }


def get_app_or_404(app_id: int) -> ManagedApp:
    managed_app = repo.get_app(app_id)
    if managed_app is None:
        raise HTTPException(status_code=404, detail="应用不存在。")
    return managed_app


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "请求失败。"
    if exc.status_code == 401 and detail == "Authentication required":
        detail = "请先登录后再操作。"
    return JSONResponse({"error": detail}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse({"error": "请求参数不合法，请检查后重试。"}, status_code=422)


@app.get("/api/auth/session")
def auth_session(request: Request) -> dict[str, bool]:
    return {"authenticated": is_authenticated(request)}


@app.post("/api/auth/login")
def auth_login(request: Request, payload: LoginPayload) -> dict[str, bool]:
    password_matches = secrets.compare_digest(
        payload.password.encode("utf-8"),
        settings.admin_password.encode("utf-8"),
    )
    if not password_matches:
        raise HTTPException(status_code=401, detail="密码错误，请重试。")
    request.session["authenticated"] = True
    return {"authenticated": True}


@app.post("/api/auth/logout")
def auth_logout(request: Request) -> dict[str, bool]:
    request.session.clear()
    return {"ok": True}


@app.get("/api/apps")
def list_apps(_: None = Depends(require_auth)) -> dict[str, object]:
    return {"apps": [app_payload(managed_app) for managed_app in repo.list_apps()]}


@app.post("/api/apps", status_code=201)
def create_app(payload: CreateAppPayload, _: None = Depends(require_auth)) -> dict[str, object]:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="应用名称不能为空。")
    created = repo.create_app(name)
    manager.app_dir(created)
    return app_payload(created)


@app.get("/api/apps/{app_id}")
def app_detail(app_id: int, _: None = Depends(require_auth)) -> dict[str, object]:
    return app_payload(get_app_or_404(app_id))


@app.delete("/api/apps/{app_id}")
def delete_app(app_id: int, _: None = Depends(require_auth)) -> dict[str, bool]:
    get_app_or_404(app_id)
    manager.delete(app_id)
    return {"ok": True}


@app.post("/api/apps/{app_id}/start")
def start_app(app_id: int, _: None = Depends(require_auth)) -> dict[str, object]:
    get_app_or_404(app_id)
    manager.start(app_id, install=True)
    return app_payload(get_app_or_404(app_id))


@app.post("/api/apps/{app_id}/stop")
def stop_app(app_id: int, _: None = Depends(require_auth)) -> dict[str, object]:
    get_app_or_404(app_id)
    manager.stop(app_id, desired=False)
    return app_payload(get_app_or_404(app_id))


@app.post("/api/apps/{app_id}/restart")
def restart_app(app_id: int, _: None = Depends(require_auth)) -> dict[str, object]:
    get_app_or_404(app_id)
    manager.restart(app_id)
    return app_payload(get_app_or_404(app_id))


@app.post("/api/apps/{app_id}/upload")
async def upload_script(
    app_id: int,
    file: UploadFile = File(...),
    manual_dependencies: str = Form(""),
    _: None = Depends(require_auth),
) -> dict[str, object]:
    managed_app = get_app_or_404(app_id)
    if not file.filename or not file.filename.endswith(".py"):
        raise HTTPException(status_code=400, detail="仅支持上传 .py 文件。")

    app_dir = manager.app_dir(managed_app)
    pending_path = app_dir / f".pending-upload-{uuid.uuid4().hex}.py"
    with pending_path.open("wb") as output:
        shutil.copyfileobj(file.file, output)

    repo.set_progress(app_id, "upload_received", 25, "上传完成，等待处理...")
    threading.Thread(
        target=_process_uploaded_script,
        args=(app_id, pending_path, manual_dependencies),
        daemon=True,
    ).start()
    return {"accepted": True, "app_id": app_id}


def _process_uploaded_script(app_id: int, pending_path: Path, manual_dependencies: str) -> None:
    managed_app = repo.get_app(app_id)
    if managed_app is None:
        return

    def progress(stage: str, percent: int, message: str) -> None:
        repo.set_progress(app_id, stage, percent, message)

    try:
        with manager.lock:
            progress("upload_received", 25, "上传完成，正在停止当前应用...")
            if not manager.stop(app_id, desired=False, reset_progress=False):
                progress("failed", 100, "无法停止当前应用，未覆盖脚本。")
                return
            repo.set_status(app_id, "installing", pid=None)
            progress("parsing", 35, "正在解析依赖...")
            inferred = infer_dependencies(pending_path)
            script_path = manager.app_dir(managed_app) / "main.py"
            pending_path.replace(script_path)
            repo.update_upload(app_id, "main.py", manual_dependencies, inferred)
            progress("venv", 45, "正在准备虚拟环境...")
            manager.start(app_id, install=True, progress=progress)
    except SyntaxError as exc:
        repo.set_status(app_id, "error", f"Python syntax error: {exc}", pid=None)
        repo.set_progress(app_id, "failed", 100, "Python 语法错误，请检查上传文件。")
    except Exception as exc:
        repo.set_status(app_id, "error", f"Upload processing failed: {exc}", pid=None)
        repo.set_progress(app_id, "failed", 100, "上传处理失败，请查看日志。")
    finally:
        if pending_path.exists():
            pending_path.unlink()


@app.get("/api/apps/{app_id}/download")
def download_script(app_id: int, _: None = Depends(require_auth)) -> Response:
    managed_app = get_app_or_404(app_id)
    script_path = manager.script_path(managed_app)
    if script_path is None or not script_path.exists():
        raise HTTPException(status_code=404, detail="当前应用尚未上传脚本。")
    return FileResponse(
        script_path,
        media_type="text/x-python",
        filename=managed_app.script_name or "main.py",
    )


@app.get("/api/apps/{app_id}/logs")
def app_logs(app_id: int, _: None = Depends(require_auth)) -> dict[str, str]:
    return {"logs": manager.read_log_tail(get_app_or_404(app_id))}


@app.get("/api/settings")
def get_settings(_: None = Depends(require_auth)) -> dict[str, object]:
    return settings_payload()


@app.put("/api/settings")
def update_settings(payload: SettingsPayload, _: None = Depends(require_auth)) -> dict[str, object]:
    if payload.source == "custom":
        ok, message = validate_mirror_url(payload.custom_url)
        if not ok:
            raise HTTPException(status_code=400, detail=message)
        url = normalize_mirror_url(payload.custom_url)
    elif get_preset(payload.source) is not None:
        url = selector_url(payload.source, payload.custom_url)
    else:
        raise HTTPException(status_code=400, detail="未知的镜像源选项。")

    repo.set_setting(PIP_INDEX_SELECTOR_SETTING_KEY, payload.source)
    repo.set_setting(PIP_INDEX_URL_SETTING_KEY, url)
    return settings_payload()


@app.get("/{full_path:path}", include_in_schema=False)
def spa_entry(full_path: str) -> Response:
    if (
        full_path == "api"
        or full_path.startswith("api/")
        or full_path == "static"
        or full_path.startswith("static/")
    ):
        raise HTTPException(status_code=404, detail="Not found")
    if not FRONTEND_INDEX.exists():
        return HTMLResponse(
            "<!doctype html><html lang='zh-CN'><meta charset='utf-8'>"
            "<title>前端尚未构建</title>"
            "<body style='font-family:system-ui;background:#060a14;color:#e2e8f0;padding:3rem'>"
            "<h1>前端尚未构建</h1>"
            "<p>请运行 <code>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</code> 后重启服务。</p>"
            "</body></html>",
            status_code=503,
        )
    return FileResponse(FRONTEND_INDEX)
