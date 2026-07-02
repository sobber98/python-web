from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import threading
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

    def start(self, app_id: int, install: bool = True) -> None:
        app = self._require_app(app_id)
        script_path = self.script_path(app)
        if script_path is None or not script_path.exists():
            self.repo.set_status(app_id, "error", "Upload a Python file before starting.")
            return

        with self.lock:
            self.stop(app_id, desired=False)
            self.repo.set_status(app_id, "installing" if install else "starting")
            if install:
                ok = self.install_dependencies(app)
                if not ok:
                    self.repo.set_desired_running(app_id, False)
                    return

            log_file = self.log_path(app).open("ab", buffering=0)
            try:
                process = subprocess.Popen(
                    [str(self.venv_python(app)), str(script_path)],
                    cwd=str(self.app_dir(app)),
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            finally:
                log_file.close()
            self.processes[app_id] = process
            self.repo.set_desired_running(app_id, True)
            self.repo.set_status(app_id, "running", pid=process.pid)
            threading.Thread(target=self._watch_process, args=(app_id, process), daemon=True).start()

    def stop(self, app_id: int, desired: bool = False) -> None:
        with self.lock:
            process = self.processes.pop(app_id, None)
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            elif process is None:
                if not self._stop_persisted_process(app_id):
                    return
            self.repo.set_desired_running(app_id, desired)
            self.repo.set_status(app_id, "stopped", pid=None)

    def restart(self, app_id: int) -> None:
        self.start(app_id, install=True)

    def delete(self, app_id: int) -> None:
        app = self.repo.get_app(app_id)
        if app is None:
            return
        self.stop(app_id, desired=False)
        shutil.rmtree(self.app_dir(app), ignore_errors=True)
        self.repo.delete_app(app_id)

    def restore_desired(self) -> None:
        for app in self.repo.list_apps():
            if app.desired_running:
                try:
                    self.start(app.id, install=False)
                except Exception as exc:  # keep one failed app from blocking startup
                    self.repo.set_status(app.id, "error", f"Restore failed: {exc}", pid=None)

    def install_dependencies(self, app: ManagedApp) -> bool:
        app_dir = self.app_dir(app)
        venv_python = self.venv_python(app)
        install_log = self.install_log_path(app)
        install_log.parent.mkdir(parents=True, exist_ok=True)
        dependencies = merge_dependencies(app.inferred_list, app.manual_dependencies)
        with install_log.open("ab") as log:
            try:
                if not venv_python.exists():
                    subprocess.run([sys.executable, "-m", "venv", str(app_dir / ".venv")], check=True, stdout=log, stderr=subprocess.STDOUT)
                if dependencies:
                    subprocess.run([str(venv_python), "-m", "pip", "install", *dependencies], check=True, stdout=log, stderr=subprocess.STDOUT)
            except subprocess.CalledProcessError as exc:
                self.repo.set_status(app.id, "error", f"Dependency install failed with exit code {exc.returncode}", pid=None)
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
                desired = self.repo.get_app(app_id).desired_running if self.repo.get_app(app_id) else False
                status = "error" if desired and code != 0 else "stopped"
                message = f"Process exited with code {code}" if code != 0 else ""
                self.repo.set_status(app_id, status, message, pid=None)

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
