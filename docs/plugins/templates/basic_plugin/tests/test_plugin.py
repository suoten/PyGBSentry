import pytest
from pygbsentry.testing import PluginTestCase
from my_plugin.main import MyPlugin


class TestMyPlugin(PluginTestCase):
    """Test cases for My Plugin"""
    
    def setUp(self):
        """Setup before each test"""
        self.plugin = MyPlugin()
        self.plugin.on_load()
    
    def test_plugin_loaded(self):
        """Test that plugin loads successfully"""
        self.assertIsNotNone(self.plugin)
        self.assertEqual(self.plugin.name, "My Plugin")
        self.assertEqual(self.plugin.version, "1.0.0")
    
    def tearDown(self):
        """Cleanup after each test"""
        self.plugin.on_unload()
