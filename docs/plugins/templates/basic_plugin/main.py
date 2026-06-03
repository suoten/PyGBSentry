"""
Main plugin logic
"""

from pygbsentry.plugins import BasePlugin


class MyPlugin(BasePlugin):
    """My Plugin Example"""
    
    name = "My Plugin"
    version = "1.0.0"
    
    def on_load(self):
        """Called when plugin is loaded"""
        self.logger.info("My Plugin loaded successfully!")
        
        # Register event hooks
        # self.hook_manager.register(
        #     EventHook.ON_DEVICE_REGISTER,
        #     self.handle_device_register
        # )
    
    def on_unload(self):
        """Called when plugin is unloaded"""
        self.logger.info("My Plugin unloaded")
    
    def on_config_update(self, config):
        """Called when configuration is updated"""
        self.logger.info(f"Configuration updated: {config}")
