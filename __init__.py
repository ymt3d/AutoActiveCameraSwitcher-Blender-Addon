import bpy
from bpy.app.handlers import persistent
from bpy.types import Operator, Panel, AddonPreferences, PropertyGroup
from bpy.props import BoolProperty, PointerProperty

bl_info = {
    "name": "Auto Active Camera Switcher",
    "blender": (4, 2, 0),
    "version": (1, 0, 2),
    "author": "Yamato3D-3dnchu.com",
    "description": "Automatically sets selected camera as active when selected.",
    "location": "View3D > Sidebar",
    "category": "3D View"
}

# Multi-language support (English and Japanese)
translations = {
    "en_US": {
        ("*", "Auto Camera Switch"): "Auto Camera Switch",
        ("*", "Enable Auto Camera Switch by Default"): "Enable Auto Camera Switch by Default",
        ("*", "Automatically set selected camera as active"): "Automatically set selected camera as active",
        ("*", "Enable Auto Camera Switcher"): "Enable Auto Camera Switcher",
    },
    "ja_JP": {
        ("*", "Auto Camera Switch"): "自動カメラ切り替え",
        ("*", "Enable Auto Camera Switch by Default"): "デフォルトで自動カメラ切り替えを有効化",
        ("*", "Automatically set selected camera as active"): "選択したカメラを自動的にアクティブにします",
        ("*", "Enable Auto Camera Switcher"): "自動カメラ切り替えを有効化",
    }
}

# Add-on preferences
class AutoActiveCameraPreferences(AddonPreferences):
    bl_idname = __package__

    default_enable: BoolProperty(
        name=bpy.app.translations.pgettext("Enable Auto Camera Switch by Default"),
        description=bpy.app.translations.pgettext("Automatically set selected camera as active when Blender starts or a new scene is loaded."),
        default=True
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "default_enable")

# Property to enable/disable the add-on functionality
class AutoActiveCameraProps(PropertyGroup):
    enable_auto_switch: BoolProperty(
        name=bpy.app.translations.pgettext("Auto Camera Switch"),
        description=bpy.app.translations.pgettext("Automatically set selected camera as active"),
        default=False
    )

# Function to switch to the selected camera when it's selected
def switch_to_active_camera(scene=None):
    obj = bpy.context.view_layer.objects.active
    if obj and obj.type == 'CAMERA':
        if bpy.context.scene.auto_active_camera_props.enable_auto_switch:
            bpy.context.scene.camera = obj

# Persistent handler for scene changes and blend file load
@persistent
def on_scene_load_post(dummy=None):
    print("Scene loaded, initializing auto camera switch...")

    # Reset auto camera switch settings based on preferences
    if bpy.context.scene:
        prefs = bpy.context.preferences.addons[__package__].preferences
        bpy.context.scene.auto_active_camera_props.enable_auto_switch = prefs.default_enable

    # Use depsgraph updates to immediately switch cameras
    if switch_to_active_camera not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(switch_to_active_camera)

# Sidebar panel
class VIEW3D_PT_auto_active_camera(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'View'
    bl_label = bpy.app.translations.pgettext("Enable Auto Camera Switcher")
    
    def draw(self, context):
        layout = self.layout
        layout.prop(context.scene.auto_active_camera_props, "enable_auto_switch")

# Add camera icon to the header of the 3D Viewport
def draw_camera_icon(self, context):
    layout = self.layout
    row = layout.row(align=True)
    props = context.scene.auto_active_camera_props
    icon = 'OUTLINER_OB_CAMERA' if props.enable_auto_switch else 'OUTLINER_DATA_CAMERA'
    row.prop(props, "enable_auto_switch", text="", icon=icon)

def draw_camera_icon_custom(self, context):
    row = self.layout.row(align=True)
    draw_camera_icon(self, context)
    self.layout.separator_spacer()

# Adjust the icon position to the left side
def draw_camera_icon_left(self, context):
    layout = self.layout
    row = layout.row(align=True)
    draw_camera_icon(self, context)

# Register/unregister functions
def register():
    bpy.utils.register_class(AutoActiveCameraPreferences)
    bpy.utils.register_class(AutoActiveCameraProps)
    bpy.types.Scene.auto_active_camera_props = PointerProperty(type=AutoActiveCameraProps)
    bpy.utils.register_class(VIEW3D_PT_auto_active_camera)
    bpy.types.VIEW3D_HT_header.append(draw_camera_icon_left)
    
    # Add persistent handlers for scene load and camera change
    bpy.app.handlers.load_post.append(on_scene_load_post)

    # Register translations
    bpy.app.translations.register(__package__, translations)

def unregister():
    bpy.utils.unregister_class(AutoActiveCameraPreferences)
    bpy.utils.unregister_class(AutoActiveCameraProps)
    if hasattr(bpy.types.Scene, "auto_active_camera_props"):
        del bpy.types.Scene.auto_active_camera_props
    bpy.utils.unregister_class(VIEW3D_PT_auto_active_camera)
    bpy.types.VIEW3D_HT_header.remove(draw_camera_icon_left)

    # Remove handlers
    if switch_to_active_camera in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(switch_to_active_camera)
    
    if on_scene_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(on_scene_load_post)

    # Unregister translations
    bpy.app.translations.unregister(__package__)

if __name__ == "__main__":
    register()
