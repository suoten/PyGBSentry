from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class EditionPaths:
    backend_app_dir: Path
    backend_api_file: Path
    frontend_src_dir: Path
    frontend_api_dir: Path
    frontend_types_dir: Path
    frontend_views_dir: Path
    frontend_composable_dir: Path


@dataclass
class CheckConfig:
    project_root: Path
    edition_paths: dict[str, EditionPaths] = field(default_factory=dict)

    @classmethod
    def from_project_root(cls, project_root: str | Path) -> CheckConfig:
        root = Path(project_root).resolve()
        editions_root = root / "editions"

        edition_paths: dict[str, EditionPaths] = {}

        oss_backend = editions_root / "open-source" / "backend" / "app"
        oss_frontend = editions_root / "open-source" / "frontend" / "src"
        if oss_backend.exists() and oss_frontend.exists():
            edition_paths["open-source"] = EditionPaths(
                backend_app_dir=oss_backend,
                backend_api_file=oss_backend / "api" / "v1" / "api.py",
                frontend_src_dir=oss_frontend,
                frontend_api_dir=oss_frontend / "api",
                frontend_types_dir=oss_frontend / "types",
                frontend_views_dir=oss_frontend / "views",
                frontend_composable_dir=oss_frontend / "composables",
            )

        server_backend = editions_root / "server" / "backend" / "app"
        server_frontend = editions_root / "server" / "frontend" / "src"
        if server_backend.exists() and server_frontend.exists():
            edition_paths["server"] = EditionPaths(
                backend_app_dir=server_backend,
                backend_api_file=server_backend / "api" / "v1" / "api.py",
                frontend_src_dir=server_frontend,
                frontend_api_dir=server_frontend / "api",
                frontend_types_dir=server_frontend / "types",
                frontend_views_dir=server_frontend / "views",
                frontend_composable_dir=server_frontend / "composables",
            )

        return cls(project_root=root, edition_paths=edition_paths)

    def get_edition_paths(self, edition: str) -> Optional[EditionPaths]:
        return self.edition_paths.get(edition)

    def available_editions(self) -> list[str]:
        return list(self.edition_paths.keys())
