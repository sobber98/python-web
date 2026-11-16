from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest import mock

from app.database import AppRepository
from app.process_manager import ProcessManager, listening_ports


def test_stop_terminates_persisted_process_after_manager_restart(tmp_path: Path) -> None:
    repo = AppRepository(tmp_path / "manager.db")
    managed_app = repo.create_app("Worker")
    repo.set_desired_running(managed_app.id, True)

    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        start_new_session=True,
    )
    try:
        repo.set_status(managed_app.id, "running", pid=process.pid)

        manager = ProcessManager(repo, tmp_path / "data")
        manager.stop(managed_app.id, desired=False)

        deadline = time.monotonic() + 5
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)

        assert process.poll() is not None
        stopped = repo.get_app(managed_app.id)
        assert stopped is not None
        assert stopped.status == "stopped"
        assert stopped.pid is None
        assert stopped.desired_running is False
    finally:
        if process.poll() is None:
            os.killpg(process.pid, 9)
            process.wait(timeout=5)


def test_shutdown_stops_tracked_process_without_sigterm_error(tmp_path: Path) -> None:
    repo = AppRepository(tmp_path / "manager.db")
    managed_app = repo.create_app("Worker")

    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        start_new_session=True,
    )
    manager = ProcessManager(repo, tmp_path / "data")
    try:
        manager.processes[managed_app.id] = process
        repo.set_desired_running(managed_app.id, True)
        repo.set_status(managed_app.id, "running", pid=process.pid)
        watcher = threading.Thread(target=manager._watch_process, args=(managed_app.id, process), daemon=True)
        watcher.start()

        manager.shutdown()
        watcher.join(timeout=5)

        stopped = repo.get_app(managed_app.id)
        assert stopped is not None
        assert stopped.status == "stopped"
        assert stopped.pid is None
        assert stopped.desired_running is True
        assert stopped.last_error == ""
        assert process.poll() is not None
    finally:
        if process.poll() is None:
            os.killpg(process.pid, 9)
            process.wait(timeout=5)


def test_listening_ports_tracks_app_process_group() -> None:
    script = (
        "import socket, time\n"
        "sock = socket.socket()\n"
        "sock.bind(('127.0.0.1', 0))\n"
        "sock.listen()\n"
        "print(sock.getsockname()[1], flush=True)\n"
        "time.sleep(2)\n"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        port = int(process.stdout.readline().strip())
        deadline = time.monotonic() + 2
        detected: list[int] = []
        while time.monotonic() < deadline:
            detected = listening_ports([process.pid]).get(process.pid, [])
            if port in detected:
                break
            time.sleep(0.05)

        assert port in detected
    finally:
        process.wait(timeout=10)
        if process.stdout is not None:
            process.stdout.close()


def test_app_dir_is_pure_path_until_ensure_called(tmp_path: Path) -> None:
    repo = AppRepository(tmp_path / "manager.db")
    managed_app = repo.create_app("Worker")
    manager = ProcessManager(repo, tmp_path / "data")

    path = manager.app_dir(managed_app)

    assert not path.exists()
    assert manager.ensure_app_dir(managed_app).is_dir()


def test_install_dependencies_skips_when_dependencies_unchanged(tmp_path: Path) -> None:
    repo = AppRepository(tmp_path / "manager.db")
    managed_app = repo.create_app("Worker")
    repo.update_upload(managed_app.id, "main.py", "requests", ["requests"])

    manager = ProcessManager(repo, tmp_path / "data")
    app_dir = manager.ensure_app_dir(managed_app)
    venv_python = manager.venv_python(managed_app)
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("", encoding="utf-8")
    (app_dir / ".deps-hash").write_text(hashlib.sha256(b"requests").hexdigest(), encoding="utf-8")

    captured: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        captured.append(list(cmd))
        return mock.Mock(returncode=0)

    with mock.patch.object(subprocess, "run", side_effect=fake_run):
        ok = manager.install_dependencies(repo.get_app(managed_app.id))

    assert ok is True
    assert captured == []

    with mock.patch.object(subprocess, "run", side_effect=fake_run):
        ok = manager.install_dependencies(repo.get_app(managed_app.id), force=True)

    assert ok is True
    assert [cmd for cmd in captured if "pip" in cmd]
