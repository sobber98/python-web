from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from app.database import AppRepository
from app.process_manager import ProcessManager


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
