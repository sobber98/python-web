from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ManagedApp:
    id: int
    name: str
    slug: str
    script_name: str | None
    manual_dependencies: str
    inferred_dependencies: str
    status: str
    desired_running: bool
    pid: int | None
    last_error: str
    created_at: str
    updated_at: str

    @property
    def inferred_list(self) -> list[str]:
        return [line for line in self.inferred_dependencies.splitlines() if line.strip()]

    @property
    def manual_list(self) -> list[str]:
        return [line for line in self.manual_dependencies.splitlines() if line.strip()]
