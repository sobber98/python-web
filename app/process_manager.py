from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path

from app.database import AppRepository
from app.dependency_inference import merge_dependencies
from app.models import ManagedApp


class ProcessManager:
    def __init__(self, repo: AppRepository, data_dir: Path) -> None:
        self.repo = repo
        self.data_dir = data_dir
        self.processes: dict[int, subprocess.Popen[bytes]] = {}
        self.lock = threading.RLock()
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def app_dir(self, app: ManagedApp) -> Path:
        path = self.data_dir / "apps" / app.slug
        path.mkdir(parents=True, exist_ok=True)
        return path

    def script_path(self, app: ManagedApp) -> Path | None:
        if not app.script_name:
            return None
        return self.app_dir(app) / app.script_name

    def log_path(self, app: ManagedApp) -> Path:
        return self.app_dir(app) / "runtime.log"

    def install_log_path(self, app: ManagedApp) -> Path:
        return self.app_dir(app) / "install.log"

    def venv_python(self, app: ManagedApp) -> Path:
        return self.app_dir(app) / ".venv" / "bin" / "python"

    def start(
        self,
        app_id: int,
        install: bool = True,
        progress: Callable[[str, int, str], None] | None = None,
    ) -> None:
        progress_callback = progress
        if progress_callback is None:
            def progress_callback(stage: str, percent: int, message: str) -> None:
                self.repo.set_progress(app_id, stage, percent, message)

        app = self._require_app(app_id)
        script_path = self.script_path(app)
        if script_path is None or not script_path.exists():
            self.repo.set_status(app_id, "error", "Upload a Python file before starting.")
            self.repo.set_progress(app_id, "failed", 100, "请先上传 Python 文件。")
            return

        with self.lock:
            if not self.stop(app_id, desired=False, reset_progress=False):
                self.repo.set_desired_running(app_id, False)
                self.repo.set_progress(app_id, "failed", 100, "无法停止当前应用，启动已取消。")
                return
            self.repo.set_status(app_id, "installing" if install else "starting")
            if install:
                ok = self.install_dependencies(app, progress=progress_callback)
                if not ok:
                    self.repo.set_desired_running(app_id, False)
                    return

            self._progress(progress_callback, "starting", 90, "正在启动应用...")
            log_file = self.log_path(app).open("ab", buffering=0)
            try:
                process = subprocess.Popen(
                    [str(self.venv_python(app)), str(script_path)],
                    cwd=str(self.app_dir(app)),
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            except Exception as exc:
                log_file.write(f"App start failed: {exc}\n".encode("utf-8"))
                self.repo.set_desired_running(app_id, False)
                self.repo.set_status(app_id, "error", f"App start failed: {exc}", pid=None)
                self._progress(progress_callback, "failed", 100, "应用启动失败，请查看日志。")
                return
            finally:
                log_file.close()
            self.processes[app_id] = process
            self.repo.set_desired_running(app_id, True)
            self.repo.set_status(app_id, "running", pid=process.pid)
            self._progress(progress_callback, "complete", 100, "应用已启动。")
            threading.Thread(target=self._watch_process, args=(app_id, process), daemon=True).start()

    def stop(self, app_id: int, desired: bool = False, reset_progress: bool = True) -> bool:
        with self.lock:
            process = self.processes.get(app_id)
            if process and process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                except PermissionError:
                    self.repo.set_status(app_id, "error", f"Permission denied stopping process group {process.pid}", pid=process.pid)
                    return False
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    except PermissionError:
                        self.repo.set_status(app_id, "error", f"Permission denied killing process group {process.pid}", pid=process.pid)
                        return False
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.repo.set_status(app_id, "error", f"Timed out stopping process group {process.pid}", pid=process.pid)
                        return False
                self.processes.pop(app_id, None)
            elif process is not None:
                self.processes.pop(app_id, None)
            elif process is None:
                if not self._stop_persisted_process(app_id):
                    return False
            self.repo.set_desired_running(app_id, desired)
            self.repo.set_status(app_id, "stopped", pid=None)
            if reset_progress:
                self.repo.set_progress(app_id, "idle", 0, "")
            return True

    def restart(self, app_id: int) -> None:
        self.start(app_id, install=True)

    def delete(self, app_id: int) -> None:
        app = self.repo.get_app(app_id)
        if app is None:
            return
        if not self.stop(app_id, desired=False):
            return
        shutil.rmtree(self.app_dir(app), ignore_errors=True)
        self.repo.delete_app(app_id)

    def restore_desired(self) -> None:
        for app in self.repo.list_apps():
            if app.desired_running:
                try:
                    self.start(app.id, install=False)
                except Exception as exc:  # keep one failed app from blocking startup
                    self.repo.set_status(app.id, "error", f"Restore failed: {exc}", pid=None)

    def shutdown(self) -> None:
        with self.lock:
            app_ids = list(self.processes)
        for app_id in app_ids:
            self.stop(app_id, desired=True, reset_progress=False)

    def install_dependencies(
        self,
        app: ManagedApp,
        progress: Callable[[str, int, str], None] | None = None,
    ) -> bool:
        app_dir = self.app_dir(app)
        venv_python = self.venv_python(app)
        install_log = self.install_log_path(app)
        install_log.parent.mkdir(parents=True, exist_ok=True)
        dependencies = merge_dependencies(app.inferred_list, app.manual_dependencies)
        with install_log.open("ab") as log:
            try:
                if not venv_python.exists():
                    self._progress(progress, "venv", 45, "正在创建应用虚拟环境...")
                    subprocess.run([sys.executable, "-m", "venv", str(app_dir / ".venv")], check=True, stdout=log, stderr=subprocess.STDOUT)
                if dependencies:
                    self._progress(progress, "installing", 70, "正在安装依赖...")
                    subprocess.run([str(venv_python), "-m", "pip", "install", *dependencies], check=True, stdout=log, stderr=subprocess.STDOUT)
                else:
                    self._progress(progress, "installing", 80, "没有需要安装的依赖。")
            except subprocess.CalledProcessError as exc:
                self.repo.set_status(app.id, "error", f"Dependency install failed with exit code {exc.returncode}", pid=None)
                self.repo.set_progress(app.id, "failed", 100, "依赖安装失败，请查看安装日志。")
                return False
            except OSError as exc:
                log.write(f"Dependency install failed: {exc}\n".encode("utf-8"))
                self.repo.set_status(app.id, "error", f"Dependency install failed: {exc}", pid=None)
                self.repo.set_progress(app.id, "failed", 100, "依赖安装失败，请查看安装日志。")
                return False
        return True

    def read_log_tail(self, app: ManagedApp, limit: int = 20000) -> str:
        output = []
        for path in [self.install_log_path(app), self.log_path(app)]:
            if path.exists():
                data = path.read_bytes()[-limit:]
                output.append(data.decode("utf-8", errors="replace"))
        return "\n".join(output).strip()

    def _watch_process(self, app_id: int, process: subprocess.Popen[bytes]) -> None:
        code = process.wait()
        with self.lock:
            if self.processes.get(app_id) is process:
                self.processes.pop(app_id, None)
                app = self.repo.get_app(app_id)
                desired = app.desired_running if app else False
                status = "error" if desired and code != 0 else "stopped"
                message = f"Process exited with code {code}" if code != 0 else ""
                self.repo.set_status(app_id, status, message, pid=None)
                if status == "error":
                    self.repo.set_progress(app_id, "failed", 100, "应用异常退出，请查看日志。")
                elif desired:
                    self.repo.set_progress(app_id, "idle", 0, "")

    def _stop_persisted_process(self, app_id: int) -> bool:
        app = self.repo.get_app(app_id)
        if app is None or app.pid is None:
            return True
        try:
            os.killpg(app.pid, signal.SIGTERM)
        except ProcessLookupError:
            return True
        except PermissionError:
            self.repo.set_status(app_id, "error", f"Permission denied stopping process group {app.pid}", pid=app.pid)
            return False

        try:
            os.waitpid(app.pid, 0)
            return True
        except ChildProcessError:
            # The process may be an orphan from a previous manager process. Poll the
            # process group instead of assuming the stale database PID is stopped.
            pass

        for _ in range(50):
            try:
                os.killpg(app.pid, 0)
            except ProcessLookupError:
                return True
            threading.Event().wait(0.1)

        try:
            os.killpg(app.pid, signal.SIGKILL)
        except ProcessLookupError:
            return True
        except PermissionError:
            self.repo.set_status(app_id, "error", f"Permission denied killing process group {app.pid}", pid=app.pid)
            return False
        return True

    def _require_app(self, app_id: int) -> ManagedApp:
        app = self.repo.get_app(app_id)
        if app is None:
            raise ValueError(f"app not found: {app_id}")
        return app

    def _progress(self, progress: Callable[[str, int, str], None] | None, stage: str, percent: int, message: str) -> None:
        if progress:
            progress(stage, percent, message)
