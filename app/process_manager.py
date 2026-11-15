from __future__ import annotations

import hashlib
import os
import shutil
import signal
import subprocess
import sys
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.database import AppRepository, PIP_INDEX_URL_SETTING_KEY
from app.dependency_inference import merge_dependencies
from app.models import ManagedApp
from app.pip_mirror import build_pip_index_args


MAX_LOG_BYTES = 5 * 1024 * 1024
DEPENDENCY_MARKER = ".deps-hash"


def _rotate_log(path: Path, max_bytes: int = MAX_LOG_BYTES) -> None:
    try:
        if path.exists() and path.stat().st_size >= max_bytes:
            backup = path.with_name(f"{path.name}.1")
            backup.unlink(missing_ok=True)
            path.replace(backup)
    except OSError:
        pass


def _dependency_fingerprint(dependencies: list[str]) -> str:
    return hashlib.sha256("\n".join(dependencies).encode("utf-8")).hexdigest()


def _read_dependency_marker(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _write_dependency_marker(path: Path, fingerprint: str) -> None:
    try:
        path.write_text(fingerprint, encoding="utf-8")
    except OSError:
        pass


class ProcessManager:
    def __init__(self, repo: AppRepository, data_dir: Path) -> None:
        self.repo = repo
        self.data_dir = data_dir
        self.processes: dict[int, subprocess.Popen[bytes]] = {}
        # 每个应用一把可重入锁，互不阻塞；进程字典与锁表共用一把短锁保护。
        self._app_locks: dict[int, threading.RLock] = {}
        self._registry_lock = threading.RLock()
        # 依赖安装串行执行，避免多个应用同时 pip 抢带宽和磁盘。
        self._install_slots = threading.Semaphore(1)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def app_lock(self, app_id: int) -> threading.RLock:
        with self._registry_lock:
            lock = self._app_locks.get(app_id)
            if lock is None:
                lock = threading.RLock()
                self._app_locks[app_id] = lock
            return lock

    def app_dir(self, app: ManagedApp) -> Path:
        # 纯路径计算，不做文件系统写操作，避免只读接口意外重建目录。
        return self.data_dir / "apps" / app.slug

    def ensure_app_dir(self, app: ManagedApp) -> Path:
        path = self.app_dir(app)
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
        force_install: bool = False,
    ) -> ManagedApp:
        progress_callback = progress
        if progress_callback is None:
            def progress_callback(stage: str, percent: int, message: str) -> None:
                self.repo.set_progress(app_id, stage, percent, message)

        with self.app_lock(app_id):
            app = self._require_app(app_id)
            script_path = self.script_path(app)
            if script_path is None or not script_path.exists():
                self.repo.set_status_with_progress(
                    app_id,
                    "error",
                    "Upload a Python file before starting.",
                    "failed",
                    100,
                    "请先上传 Python 文件。",
                )
                return self._reload(app_id)

            if not self.stop(app_id, desired=False, reset_progress=False):
                self.repo.set_desired_running(app_id, False)
                self.repo.set_progress(app_id, "failed", 100, "无法停止当前应用，启动已取消。")
                return self._reload(app_id)

            self.repo.set_status(app_id, "installing" if install else "starting")
            if install:
                ok = self.install_dependencies(app, progress=progress_callback, force=force_install)
                if not ok:
                    self.repo.set_desired_running(app_id, False)
                    return self._reload(app_id)

            self._progress(progress_callback, "starting", 90, "正在启动应用...")
            self.ensure_app_dir(app)
            log_path = self.log_path(app)
            _rotate_log(log_path)
            log_file = log_path.open("ab", buffering=0)
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
                self.repo.set_status_with_progress(
                    app_id,
                    "error",
                    f"App start failed: {exc}",
                    "failed",
                    100,
                    "应用启动失败，请查看日志。",
                )
                return self._reload(app_id)
            finally:
                log_file.close()
            with self._registry_lock:
                self.processes[app_id] = process
            self.repo.set_desired_running(app_id, True)
            self.repo.set_status(app_id, "running", pid=process.pid)
            self._progress(progress_callback, "complete", 100, "应用已启动。")
            threading.Thread(target=self._watch_process, args=(app_id, process), daemon=True).start()
            return self._reload(app_id)

    def stop(self, app_id: int, desired: bool = False, reset_progress: bool = True) -> bool:
        with self.app_lock(app_id):
            with self._registry_lock:
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
                with self._registry_lock:
                    self.processes.pop(app_id, None)
            elif process is not None:
                with self._registry_lock:
                    self.processes.pop(app_id, None)
            elif process is None:
                if not self._stop_persisted_process(app_id):
                    return False
            self.repo.set_desired_running(app_id, desired)
            self.repo.set_status(app_id, "stopped", pid=None)
            if reset_progress:
                self.repo.set_progress(app_id, "idle", 0, "")
            return True

    def restart(self, app_id: int) -> ManagedApp:
        return self.start(app_id, install=True)

    def delete(self, app_id: int) -> None:
        with self.app_lock(app_id):
            app = self.repo.get_app(app_id)
            if app is None:
                return
            if not self.stop(app_id, desired=False):
                return
            shutil.rmtree(self.app_dir(app), ignore_errors=True)
            self.repo.delete_app(app_id)

    def restore_desired(self) -> None:
        pending = [app for app in self.repo.list_apps() if app.desired_running]
        if not pending:
            return
        # 并行恢复，启动耗时取决于最慢的一个应用而不是全部之和。
        with ThreadPoolExecutor(max_workers=min(4, len(pending))) as pool:
            list(pool.map(self._restore_app, pending))

    def _restore_app(self, app: ManagedApp) -> None:
        try:
            self.start(app.id, install=False)
        except Exception as exc:  # keep one failed app from blocking startup
            self.repo.set_status(app.id, "error", f"Restore failed: {exc}", pid=None)

    def shutdown(self) -> None:
        with self._registry_lock:
            app_ids = list(self.processes)
        if not app_ids:
            return
        with ThreadPoolExecutor(max_workers=min(4, len(app_ids))) as pool:
            list(pool.map(self._stop_for_shutdown, app_ids))

    def _stop_for_shutdown(self, app_id: int) -> None:
        try:
            self.stop(app_id, desired=True, reset_progress=False)
        except Exception:
            # 停机阶段单个应用失败不应阻断其它应用退出。
            pass

    def install_dependencies(
        self,
        app: ManagedApp,
        progress: Callable[[str, int, str], None] | None = None,
        force: bool = False,
    ) -> bool:
        with self._install_slots:
            return self._install_dependencies(app, progress, force)

    def _install_dependencies(
        self,
        app: ManagedApp,
        progress: Callable[[str, int, str], None] | None = None,
        force: bool = False,
    ) -> bool:
        app_dir = self.ensure_app_dir(app)
        venv_python = self.venv_python(app)
        install_log = self.install_log_path(app)
        _rotate_log(install_log)
        dependencies = merge_dependencies(app.inferred_list, app.manual_dependencies)
        fingerprint = _dependency_fingerprint(dependencies)
        marker = app_dir / DEPENDENCY_MARKER
        with install_log.open("ab") as log:
            try:
                created_venv = False
                if not venv_python.exists():
                    self._progress(progress, "venv", 45, "正在创建应用虚拟环境...")
                    subprocess.run([sys.executable, "-m", "venv", str(app_dir / ".venv")], check=True, stdout=log, stderr=subprocess.STDOUT)
                    created_venv = True
                if dependencies:
                    if not force and not created_venv and _read_dependency_marker(marker) == fingerprint:
                        self._progress(progress, "installing", 80, "依赖未变化，跳过安装。")
                    else:
                        self._progress(progress, "installing", 70, "正在安装依赖...")
                        pip_cmd = [str(venv_python), "-m", "pip", "install", *dependencies]
                        index_url = self.repo.get_setting(PIP_INDEX_URL_SETTING_KEY, "")
                        pip_cmd.extend(build_pip_index_args(index_url))
                        subprocess.run(pip_cmd, check=True, stdout=log, stderr=subprocess.STDOUT)
                        _write_dependency_marker(marker, fingerprint)
                else:
                    self._progress(progress, "installing", 80, "没有需要安装的依赖。")
                    _write_dependency_marker(marker, fingerprint)
            except subprocess.CalledProcessError as exc:
                self.repo.set_status_with_progress(
                    app.id,
                    "error",
                    f"Dependency install failed with exit code {exc.returncode}",
                    "failed",
                    100,
                    "依赖安装失败，请查看安装日志。",
                )
                return False
            except OSError as exc:
                log.write(f"Dependency install failed: {exc}\n".encode("utf-8"))
                self.repo.set_status_with_progress(
                    app.id,
                    "error",
                    f"Dependency install failed: {exc}",
                    "failed",
                    100,
                    "依赖安装失败，请查看安装日志。",
                )
                return False
        return True

    def read_log_tail(self, app: ManagedApp, limit: int = 20000) -> str:
        # 安装日志只在安装中或安装失败时才有排查价值，正常运行时不重复回传。
        paths = [self.log_path(app)]
        if app.status in {"installing", "error"}:
            paths.insert(0, self.install_log_path(app))
        output = []
        for path in paths:
            if path.exists():
                data = path.read_bytes()[-limit:]
                output.append(data.decode("utf-8", errors="replace"))
        return "\n".join(output).strip()

    def _watch_process(self, app_id: int, process: subprocess.Popen[bytes]) -> None:
        code = process.wait()
        with self.app_lock(app_id):
            with self._registry_lock:
                if self.processes.get(app_id) is not process:
                    return
                self.processes.pop(app_id, None)
            app = self.repo.get_app(app_id)
            desired = app.desired_running if app else False
            status = "error" if desired and code != 0 else "stopped"
            message = f"Process exited with code {code}" if code != 0 else ""
            if status == "error":
                self.repo.set_status_with_progress(
                    app_id, status, message, "failed", 100, "应用异常退出，请查看日志。"
                )
            elif desired:
                self.repo.set_status_with_progress(app_id, status, message, "idle", 0, "")
            else:
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
        return self._reload(app_id)

    def _reload(self, app_id: int) -> ManagedApp:
        app = self.repo.get_app(app_id)
        if app is None:
            raise ValueError(f"app not found: {app_id}")
        return app

    def _progress(self, progress: Callable[[str, int, str], None] | None, stage: str, percent: int, message: str) -> None:
        if progress:
            progress(stage, percent, message)
