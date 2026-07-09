"""tests for tools.system_check.shared.check_config — CheckConfig.from_project_root()。"""

from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from tools.system_check.shared.check_config import CheckConfig, EditionPaths


# 真实项目根目录（包含 editions/、tools/ 等的目录）
# __file__ = .../editions/open-source/tools/system_check/tests/test_check_config.py
# parents[5] = .../PyGBSentry  （包含 editions/ 目录）
PROJECT_ROOT = Path(__file__).resolve().parents[5]


class TestFromProjectRootRealProject(unittest.TestCase):
    """使用真实项目根目录验证 CheckConfig.from_project_root()。"""

    @classmethod
    def setUpClass(cls):
        cls.config = CheckConfig.from_project_root(PROJECT_ROOT)

    def test_project_root_resolved(self):
        self.assertEqual(self.config.project_root, PROJECT_ROOT.resolve())

    def test_open_source_edition_detected(self):
        """真实项目下应能识别出 open-source 版本。"""
        self.assertIn("open-source", self.config.edition_paths)

    def test_server_edition_detected(self):
        """真实项目下应能识别出 server 版本（仓库同时包含 editions/server）。"""
        self.assertIn("server", self.config.edition_paths)

    def test_available_editions(self):
        available = self.config.available_editions()
        self.assertIn("open-source", available)
        self.assertIn("server", available)

    def test_get_edition_paths_returns_editionpaths(self):
        paths = self.config.get_edition_paths("open-source")
        self.assertIsNotNone(paths)
        self.assertIsInstance(paths, EditionPaths)

    def test_get_edition_paths_unknown_returns_none(self):
        self.assertIsNone(self.config.get_edition_paths("nonexistent-edition"))

    def test_open_source_paths_point_to_existing_dirs(self):
        paths = self.config.get_edition_paths("open-source")
        self.assertIsNotNone(paths)
        self.assertTrue(paths.backend_app_dir.exists(), f"{paths.backend_app_dir} 应存在")
        self.assertTrue(paths.frontend_src_dir.exists(), f"{paths.frontend_src_dir} 应存在")

    def test_open_source_paths_structure(self):
        paths = self.config.get_edition_paths("open-source")
        self.assertIsNotNone(paths)
        # 关键路径字段全部设置且指向 editions/open-source 下
        self.assertTrue(str(paths.backend_app_dir).endswith(str(Path("editions") / "open-source" / "backend" / "app")))
        self.assertTrue(str(paths.frontend_src_dir).endswith(str(Path("editions") / "open-source" / "frontend" / "src")))
        self.assertTrue(str(paths.backend_api_file).endswith(str(Path("api") / "v1" / "api.py")))
        self.assertTrue(str(paths.frontend_api_dir).endswith("api"))
        self.assertTrue(str(paths.frontend_types_dir).endswith("types"))
        self.assertTrue(str(paths.frontend_views_dir).endswith("views"))
        self.assertTrue(str(paths.frontend_composable_dir).endswith("composables"))


class TestFromProjectRootWithTempDir(unittest.TestCase):
    """使用临时目录验证：当 editions 结构缺失时不应识别任何版本。"""

    def test_no_editions_returns_empty_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = CheckConfig.from_project_root(tmp)
            self.assertEqual(config.edition_paths, {})
            self.assertEqual(config.available_editions(), [])
            self.assertIsNone(config.get_edition_paths("open-source"))

    def test_only_open_source_edition_detected(self):
        """仅存在 open-source 目录时只识别 open-source。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "editions" / "open-source" / "backend" / "app").mkdir(parents=True)
            (root / "editions" / "open-source" / "frontend" / "src").mkdir(parents=True)
            # server 目录不创建
            config = CheckConfig.from_project_root(root)
            self.assertEqual(list(config.edition_paths.keys()), ["open-source"])
            self.assertNotIn("server", config.edition_paths)

    def test_missing_one_half_not_detected(self):
        """只有 backend 没有 frontend 时不应识别该版本。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "editions" / "open-source" / "backend" / "app").mkdir(parents=True)
            # frontend/src 不创建
            config = CheckConfig.from_project_root(root)
            self.assertNotIn("open-source", config.edition_paths)

    def test_accepts_string_path(self):
        """from_project_root 应同时接受 str 与 Path。"""
        config_str = CheckConfig.from_project_root(str(PROJECT_ROOT))
        config_path = CheckConfig.from_project_root(PROJECT_ROOT)
        self.assertIn("open-source", config_str.edition_paths)
        self.assertIn("open-source", config_path.edition_paths)


if __name__ == "__main__":
    unittest.main()
