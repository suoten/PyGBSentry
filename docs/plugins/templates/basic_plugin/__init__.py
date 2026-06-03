"""
My Plugin for PyGBSentry
"""

from .main import MyPlugin


def register(plugin_manager):
    """
    Plugin registration function (required)
    
    Args:
        plugin_manager: PyGBSentry plugin manager instance
        
    Returns:
        Plugin instance
    """
    plugin = MyPlugin()
    plugin_manager.register_plugin(plugin)
    
    return plugin
