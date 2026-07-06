from __future__ import annotations

import shutil
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.config import load_settings
from app.database import AppRepository
from app.dependency_inference import infer_dependencies
from app.process_manager import ProcessManager

settings = load_settings()
repo = AppRepository(settings.db_path)
manager = ProcessManager(repo, settings.data_dir)
APP_DIR = Path(__file__).resolve().parent


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
templates = Jinja2Templates(directory=APP_DIR / "templates")


def is_authenticated(request: Request) -> bool:
    return bool(request.session.get("authenticated"))


def require_auth(request: Request) -> None:
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Authentication required")


def require_page_auth(request: Request) -> None:
    if not is_authenticated(request):
        raise HTTPException(status_code=303, headers={"Location": "/login"})


@app.exception_handler(HTTPException)
async def redirect_unauthenticated(request: Request, exc: HTTPException):
    if exc.status_code == 303 and exc.headers and "Location" in exc.headers:
        return RedirectResponse(exc.headers["Location"], status_code=303)
    if exc.status_code == 401 and request.url.path.startswith("/api/"):
        return JSONResponse({"error": exc.detail}, status_code=401)
    if exc.status_code == 401:
        return RedirectResponse("/login", status_code=303)
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {"error": ""})


@app.post("/login")
async def login(request: Request, password: str = Form(...)) -> Response:
    if password == settings.admin_password:
        request.session["authenticated"] = True
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": "Invalid password"}, status_code=401)


@app.post("/logout")
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, _: None = Depends(require_page_auth)) -> HTMLResponse:
    apps = repo.list_apps()
    selected = apps[0] if apps else None
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"apps": apps, "selected": selected, "logs": manager.read_log_tail(selected) if selected else ""},
    )


@app.get("/apps/{app_id}", response_class=HTMLResponse)
def app_detail(request: Request, app_id: int, _: None = Depends(require_page_auth)) -> HTMLResponse:
    selected = repo.get_app(app_id)
    if selected is None:
        raise HTTPException(status_code=404, detail="App not found")
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"apps": repo.list_apps(), "selected": selected, "logs": manager.read_log_tail(selected)},
    )


@app.post("/apps")
def create_app(name: str = Form(...), _: None = Depends(require_page_auth)) -> RedirectResponse:
    if not name.strip():
        raise HTTPException(status_code=400, detail="App name is required")
    created = repo.create_app(name)
    manager.app_dir(created)
    return RedirectResponse(f"/apps/{created.id}", status_code=303)


@app.post("/apps/{app_id}/upload")
async def upload_script(
    request: Request,
    app_id: int,
    file: UploadFile = File(...),
    manual_dependencies: str = Form(""),
    _: None = Depends(require_page_auth),
) -> Response:
    managed_app = repo.get_app(app_id)
    if managed_app is None:
        raise HTTPException(status_code=404, detail="App not found")
    if not file.filename or not file.filename.endswith(".py"):
        raise HTTPException(status_code=400, detail="Only .py files are supported")

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

    if _wants_json(request):
        return JSONResponse({"accepted": True, "app_id": app_id})
    return RedirectResponse(f"/apps/{app_id}", status_code=303)


def _wants_json(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    requested_with = request.headers.get("x-requested-with", "")
    return "application/json" in accept or requested_with == "XMLHttpRequest"


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


@app.post("/apps/{app_id}/start")
def start_app(app_id: int, _: None = Depends(require_page_auth)) -> RedirectResponse:
    if repo.get_app(app_id) is None:
        raise HTTPException(status_code=404, detail="App not found")
    manager.start(app_id, install=True)
    return RedirectResponse(f"/apps/{app_id}", status_code=303)


@app.post("/apps/{app_id}/stop")
def stop_app(app_id: int, _: None = Depends(require_page_auth)) -> RedirectResponse:
    if repo.get_app(app_id) is None:
        raise HTTPException(status_code=404, detail="App not found")
    manager.stop(app_id, desired=False)
    return RedirectResponse(f"/apps/{app_id}", status_code=303)


@app.post("/apps/{app_id}/restart")
def restart_app(app_id: int, _: None = Depends(require_page_auth)) -> RedirectResponse:
    if repo.get_app(app_id) is None:
        raise HTTPException(status_code=404, detail="App not found")
    manager.restart(app_id)
    return RedirectResponse(f"/apps/{app_id}", status_code=303)


@app.post("/apps/{app_id}/delete")
def delete_app(app_id: int, _: None = Depends(require_page_auth)) -> RedirectResponse:
    if repo.get_app(app_id) is None:
        raise HTTPException(status_code=404, detail="App not found")
    manager.delete(app_id)
    return RedirectResponse("/", status_code=303)


@app.get("/api/apps/{app_id}/status")
def app_status(app_id: int, _: None = Depends(require_auth)) -> dict[str, object]:
    managed_app = repo.get_app(app_id)
    if managed_app is None:
        raise HTTPException(status_code=404, detail="App not found")
    return {
        "id": managed_app.id,
        "name": managed_app.name,
        "status": managed_app.status,
        "desired_running": managed_app.desired_running,
        "pid": managed_app.pid,
        "last_error": managed_app.last_error,
        "progress_stage": managed_app.progress_stage,
        "progress_percent": managed_app.progress_percent,
        "progress_message": managed_app.progress_message,
        "inferred_dependencies": managed_app.inferred_list,
        "manual_dependencies": managed_app.manual_list,
    }


@app.get("/api/apps/{app_id}/logs")
def app_logs(app_id: int, _: None = Depends(require_auth)) -> dict[str, str]:
    managed_app = repo.get_app(app_id)
    if managed_app is None:
        raise HTTPException(status_code=404, detail="App not found")
    return {"logs": manager.read_log_tail(managed_app)}
