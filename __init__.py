# SPDX-License-Identifier: GPL-3.0-or-later
#
# Auto Active Camera Switcher
# Automatically makes the selected camera the active scene camera.
#
# NOTE: Metadata lives in blender_manifest.toml (Blender 4.2+ extension format).
#       bl_info is intentionally omitted.

import bpy
from bpy.app.handlers import persistent
from bpy.types import AddonPreferences, Panel, PropertyGroup
from bpy.props import BoolProperty, PointerProperty

bl_info = {
    "name": "Auto Active Camera Switcher",
    "blender": (4, 2, 0),
    "version": (1, 1, 0),
    "author": "Yamato3D-3dnchu.com",
    "description": "Automatically sets selected camera as active when selected.",
    "location": "View3D > Sidebar",
    "category": "3D View"
}

# --------------------------------------------------------------------------
# Module state
# --------------------------------------------------------------------------

# Unique owner token for msgbus subscriptions.
_msgbus_owner = object()

# True while a render job is running. We never touch scene.camera during renders.
_is_rendering = False

# True when a deferred update is already queued, so we never stack timers.
_update_pending = False


# --------------------------------------------------------------------------
# Translations
#
# IMPORTANT: do NOT call bpy.app.translations.pgettext() at class-definition
# time. At import time the translation dictionary is not registered yet, so the
# English string gets baked in permanently and never follows a language switch.
# Blender translates property `name`/`description` and `bl_label` automatically
# using the English string as the msgid, so plain strings are what we want.
# --------------------------------------------------------------------------

translations = {
    "ja_JP": {
        ("*", "Auto Camera Switch"): "自動カメラ切り替え",
        ("*", "Automatically set selected camera as active"): "選択したカメラを自動的にアクティブにします",
        ("*", "Auto Active Camera Switcher"): "自動カメラ切り替え",
        ("*", "Enable by Default"): "デフォルトで有効化",
        ("*", "Enable auto camera switching for newly opened or created files"):
            "新規作成・読み込んだファイルで自動カメラ切り替えを有効にします",
        ("*", "Apply Default on File Load"): "ファイル読み込み時に既定値を適用",
        ("*", "Overwrite the per-scene toggle every time a file is loaded. "
              "Disable to keep the setting saved in each .blend file"):
            "ファイルを読み込むたびにシーンごとの設定を上書きします。"
            "オフにすると .blend に保存された設定を維持します",
        ("*", "Require Selection"): "選択状態を必須にする",
        ("*", "Only switch when the camera is actually selected, not merely active"):
            "アクティブなだけでなく、実際に選択されているカメラのみ切り替えます",
    }
}


# --------------------------------------------------------------------------
# Preferences / Properties
# --------------------------------------------------------------------------

def _get_prefs():
    """Return this add-on's preferences, or None if unavailable."""
    try:
        return bpy.context.preferences.addons[__package__].preferences
    except (KeyError, AttributeError):
        return None


class AACS_AddonPreferences(AddonPreferences):
    bl_idname = __package__

    default_enable: BoolProperty(
        name="Enable by Default",
        description="Enable auto camera switching for newly opened or created files",
        default=True,
    )

    apply_default_on_load: BoolProperty(
        name="Apply Default on File Load",
        description=(
            "Overwrite the per-scene toggle every time a file is loaded. "
            "Disable to keep the setting saved in each .blend file"
        ),
        default=False,
    )

    require_selection: BoolProperty(
        name="Require Selection",
        description="Only switch when the camera is actually selected, not merely active",
        default=True,
    )

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.prop(self, "default_enable")
        col.prop(self, "apply_default_on_load")
        col.prop(self, "require_selection")


class AACS_Props(PropertyGroup):
    enable_auto_switch: BoolProperty(
        name="Auto Camera Switch",
        description="Automatically set selected camera as active",
        default=False,
    )


# --------------------------------------------------------------------------
# Core logic
# --------------------------------------------------------------------------

def _apply_active_camera():
    """Deferred worker.

    Runs from bpy.app.timers, i.e. from Blender's main loop, safely OUTSIDE of
    depsgraph evaluation. This is the whole point of the rewrite: assigning
    scene.camera triggers DEG_id_tag_update, which is illegal from inside a
    depsgraph handler and crashes Blender 5.x.

    Always returns None so the timer fires exactly once.
    """
    global _update_pending
    _update_pending = False

    if _is_rendering:
        return None

    context = bpy.context
    scene = getattr(context, "scene", None)
    view_layer = getattr(context, "view_layer", None)
    if scene is None or view_layer is None:
        return None

    props = getattr(scene, "auto_active_camera_props", None)
    if props is None or not props.enable_auto_switch:
        return None

    obj = view_layer.objects.active
    if obj is None or obj.type != 'CAMERA':
        return None

    prefs = _get_prefs()
    if prefs is None or prefs.require_selection:
        try:
            if not obj.select_get():
                return None
        except RuntimeError:
            # Object is not in the current view layer.
            return None

    # No-op guard. Without this we would re-tag the depsgraph on every single
    # notification, which is what made the viewport choppy (issue #1).
    if scene.camera is obj:
        return None

    scene.camera = obj
    return None


def _schedule_update():
    """Queue a single deferred update."""
    global _update_pending
    if _update_pending or _is_rendering:
        return
    _update_pending = True
    try:
        bpy.app.timers.register(_apply_active_camera, first_interval=0.0)
    except Exception:
        _update_pending = False


def _on_active_object_changed(*args):
    """msgbus notify callback. Never write data here - only schedule."""
    _schedule_update()


def _subscribe_msgbus():
    """(Re)subscribe to active-object changes."""
    bpy.msgbus.clear_by_owner(_msgbus_owner)
    bpy.msgbus.subscribe_rna(
        key=(bpy.types.LayerObjects, "active"),
        owner=_msgbus_owner,
        args=(),
        notify=_on_active_object_changed,
        options={'PERSISTENT'},
    )


# --------------------------------------------------------------------------
# Handlers
#
# Handler signatures changed across Blender versions (some receive `scene`,
# some receive `(scene, depsgraph)`). Using *args keeps this working on 4.2
# through 5.x without version checks.
# --------------------------------------------------------------------------

@persistent
def _on_load_post(*args):
    # msgbus subscriptions are cleared on file load even with PERSISTENT in
    # some versions, so always resubscribe.
    _subscribe_msgbus()

    prefs = _get_prefs()
    if prefs is None or not prefs.apply_default_on_load:
        return

    for scene in bpy.data.scenes:
        props = getattr(scene, "auto_active_camera_props", None)
        if props is not None:
            props.enable_auto_switch = prefs.default_enable


@persistent
def _on_undo_redo_post(*args):
    # Undo can drop msgbus subscriptions.
    _subscribe_msgbus()
    _schedule_update()


@persistent
def _on_render_pre(*args):
    global _is_rendering
    _is_rendering = True


@persistent
def _on_render_post(*args):
    global _is_rendering
    _is_rendering = False


# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------

class VIEW3D_PT_auto_active_camera(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'View'
    bl_label = "Auto Active Camera Switcher"

    def draw(self, context):
        layout = self.layout
        props = getattr(context.scene, "auto_active_camera_props", None)
        if props is None:
            layout.label(text="Add-on not initialized", icon='ERROR')
            return
        layout.prop(props, "enable_auto_switch")


def _draw_header_toggle(self, context):
    props = getattr(context.scene, "auto_active_camera_props", None)
    if props is None:
        return
    icon = 'OUTLINER_OB_CAMERA' if props.enable_auto_switch else 'OUTLINER_DATA_CAMERA'
    self.layout.prop(props, "enable_auto_switch", text="", icon=icon, toggle=True)


# --------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------

_classes = (
    AACS_AddonPreferences,
    AACS_Props,
    VIEW3D_PT_auto_active_camera,
)

_handler_pairs = (
    (bpy.app.handlers.load_post, _on_load_post),
    (bpy.app.handlers.undo_post, _on_undo_redo_post),
    (bpy.app.handlers.redo_post, _on_undo_redo_post),
    (bpy.app.handlers.render_init, _on_render_pre),
    (bpy.app.handlers.render_complete, _on_render_post),
    (bpy.app.handlers.render_cancel, _on_render_post),
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.auto_active_camera_props = PointerProperty(type=AACS_Props)
    bpy.types.VIEW3D_HT_header.append(_draw_header_toggle)

    for handler_list, func in _handler_pairs:
        if func not in handler_list:
            handler_list.append(func)

    try:
        bpy.app.translations.register(__package__, translations)
    except ValueError:
        # Already registered (e.g. reload during development).
        pass

    # Subscribe immediately so the add-on works the moment it is enabled,
    # not only after a file is opened.
    _subscribe_msgbus()


def unregister():
    global _is_rendering, _update_pending

    bpy.msgbus.clear_by_owner(_msgbus_owner)

    if bpy.app.timers.is_registered(_apply_active_camera):
        bpy.app.timers.unregister(_apply_active_camera)
    _update_pending = False
    _is_rendering = False

    for handler_list, func in _handler_pairs:
        if func in handler_list:
            handler_list.remove(func)

    try:
        bpy.types.VIEW3D_HT_header.remove(_draw_header_toggle)
    except Exception:
        pass

    try:
        bpy.app.translations.unregister(__package__)
    except ValueError:
        pass

    # Delete the PointerProperty BEFORE unregistering the PropertyGroup it
    # points at. The original code had this backwards.
    if hasattr(bpy.types.Scene, "auto_active_camera_props"):
        del bpy.types.Scene.auto_active_camera_props

    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
