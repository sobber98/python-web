from __future__ import annotations

import shutil
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

app = FastAPI(title="Python Management Platform")
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, same_site="lax")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.on_event("startup")
def restore_running_apps() -> None:
    manager.restore_desired()


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
    return templates.TemplateResponse("login.html", {"request": request, "error": ""})


@app.post("/login")
async def login(request: Request, password: str = Form(...)) -> Response:
    if password == settings.admin_password:
        request.session["authenticated"] = True
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid password"}, status_code=401)


@app.post("/logout")
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, _: None = Depends(require_page_auth)) -> HTMLResponse:
    apps = repo.list_apps()
    selected = apps[0] if apps else None
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "apps": apps, "selected": selected, "logs": manager.read_log_tail(selected) if selected else ""},
    )


@app.get("/apps/{app_id}", response_class=HTMLResponse)
def app_detail(request: Request, app_id: int, _: None = Depends(require_page_auth)) -> HTMLResponse:
    selected = repo.get_app(app_id)
    if selected is None:
        raise HTTPException(status_code=404, detail="App not found")
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "apps": repo.list_apps(), "selected": selected, "logs": manager.read_log_tail(selected)},
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
    app_id: int,
    file: UploadFile = File(...),
    manual_dependencies: str = Form(""),
    _: None = Depends(require_page_auth),
) -> RedirectResponse:
    managed_app = repo.get_app(app_id)
    if managed_app is None:
        raise HTTPException(status_code=404, detail="App not found")
    if not file.filename or not file.filename.endswith(".py"):
        raise HTTPException(status_code=400, detail="Only .py files are supported")

    manager.stop(app_id, desired=False)
    app_dir = manager.app_dir(managed_app)
    script_path = app_dir / "main.py"
    with script_path.open("wb") as output:
        shutil.copyfileobj(file.file, output)
    try:
        inferred = infer_dependencies(script_path)
    except SyntaxError as exc:
        repo.set_status(app_id, "error", f"Python syntax error: {exc}")
        return RedirectResponse(f"/apps/{app_id}", status_code=303)

    repo.update_upload(app_id, "main.py", manual_dependencies, inferred)
    manager.start(app_id, install=True)
    return RedirectResponse(f"/apps/{app_id}", status_code=303)


@app.post("/apps/{app_id}/start")
def start_app(app_id: int, _: None = Depends(require_page_auth)) -> RedirectResponse:
    manager.start(app_id, install=True)
    return RedirectResponse(f"/apps/{app_id}", status_code=303)


@app.post("/apps/{app_id}/stop")
def stop_app(app_id: int, _: None = Depends(require_page_auth)) -> RedirectResponse:
    manager.stop(app_id, desired=False)
    return RedirectResponse(f"/apps/{app_id}", status_code=303)


@app.post("/apps/{app_id}/restart")
def restart_app(app_id: int, _: None = Depends(require_page_auth)) -> RedirectResponse:
    manager.restart(app_id)
    return RedirectResponse(f"/apps/{app_id}", status_code=303)


@app.post("/apps/{app_id}/delete")
def delete_app(app_id: int, _: None = Depends(require_page_auth)) -> RedirectResponse:
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
        "inferred_dependencies": managed_app.inferred_list,
        "manual_dependencies": managed_app.manual_list,
    }


@app.get("/api/apps/{app_id}/logs")
def app_logs(app_id: int, _: None = Depends(require_auth)) -> dict[str, str]:
    managed_app = repo.get_app(app_id)
    if managed_app is None:
        raise HTTPException(status_code=404, detail="App not found")
    return {"logs": manager.read_log_tail(managed_app)}
