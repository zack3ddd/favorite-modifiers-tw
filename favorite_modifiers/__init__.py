# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####
#
# 原始外掛：Favorite Modifiers — 作者 Oleg Stepanov
# 本版本為延伸／繁體中文化版，創意與基礎程式碼來自 Oleg Stepanov 的 Favorite Modifiers，
# 由 Zack3D 延伸（2024-2026）。GPL 授權，原作者著作權保留。
#
# 主要延伸：
# - 繁體中文化，介面與 tooltip 隨使用者語系
# - 常用清單依物件類型分組、右鍵左移/右移
# - 偏好面板可依物件類型編輯常用清單，並與介面按鈕即時同步
# - 預設清單（defaults.json，隨外掛一起發佈）＋ 儲存/恢復/清空
#

# <pep8 compliant>


import bpy
import os
import json
from bl_ui.properties_data_modifier import DATA_PT_modifiers
from bpy.app.handlers import persistent
from bpy.props import (BoolProperty, EnumProperty, PointerProperty,
                       StringProperty)
from bpy.types import (AddonPreferences, Menu, Modifier,
                       Operator, Panel, PropertyGroup, Scene)
from bpy.utils import register_class, unregister_class

bl_info = {
    "name": "Favorite Modifiers",
    "description": "A row of favorite-modifier buttons above the modifier panel. Traditional-Chinese + extended edition; original idea from Oleg Stepanov's Favorite Modifiers.",
    "author": "Zack3D (inspired by Oleg Stepanov)",
    "version": (1, 2, 0),
    "blender": (4, 4, 0),
    "location": "Properties Editor > Modifiers",
    "warning": "",
    "wiki_url": "",
    "support": 'COMMUNITY',
    "category": "Modifiers"
}


# ─────────────────────────────────────────────────────────────
# 介面翻譯（i18n）：UI 字串用英文當原文，附繁中譯文表，跟隨 Blender 語言。
#   英文介面 → 英文；繁中／簡中介面 → 都顯示繁體（不出簡體）。
# 掛在專屬翻譯 context（避免「Clear」「Move」等通用字被 Blender 內建翻譯蓋掉）。
# 繁中同時掛四代碼：zh_HANT/zh_TW（繁）、zh_HANS/zh_CN（簡也顯示繁）。
# ─────────────────────────────────────────────────────────────
I18N_CTX = "FavoriteModifiers"

_ZH = {
    "Display Style": "顯示樣式",
    "Icon + Name": "圖示+名稱",
    "Icon": "圖示",
    "Object Type": "物件類型",
    "Mesh": "網格物體",
    "Curve / Text / Surface": "曲線／文字／曲面",
    "Lattice": "晶格物體",
    "Grease Pencil": "蠟筆物體",
    "(No favorite modifiers yet - start from 'Add Modifier' below)":
        "（尚無常用修改器，從下面「加入修改器」開始）",
    "Add Modifier": "加入修改器",
    "Save as Default": "儲存為預設",
    "Restore Default": "恢復預設",
    "Clear": "清空",
    "Move": "移動",
    "Remove": "移除",
    "Add / Remove Favorite Modifier": "新增/移除常用修改器",
    "Add to Favorite Modifiers": "加入到常用修改器",
    "Remove from Favorite Modifiers": "從常用修改器移除",
    "Move Button Left": "左移按鈕",
    "Move Button Right": "右移按鈕",
    "Press + to add a favorite modifier": "按 ＋ 加入常用修改器",
    "Add Favorite Modifier": "加入常用修改器",
    "Add Favorite Modifier by Search": "加入常用修改器",
    "Move Favorite Modifier": "移動常用修改器",
    "Saved as default": "已儲存為預設",
    "Restored to default": "已恢復成預設",
    '"%s" does not apply to the current object type': "「%s」不適用於目前的物件類型",
    "A row of favorite-modifier buttons above the modifier panel. "
    "Traditional-Chinese + extended edition; original idea from Oleg Stepanov's Favorite Modifiers.":
        "在修改器介面上方顯示常用修改器的按鈕組合。繁體中文化＋功能延伸版，原始創意來自 Oleg Stepanov 的 Favorite Modifiers。",
}

_ZH_CTX = {(I18N_CTX, en): zh for en, zh in _ZH.items()}
translations_dict = {"zh_HANT": _ZH_CTX, "zh_TW": _ZH_CTX,
                     "zh_HANS": _ZH_CTX, "zh_CN": _ZH_CTX}


def _t(msgid):
    """把英文原文翻成目前介面語言（英文介面回傳原文）。"""
    return bpy.app.translations.pgettext_iface(msgid, I18N_CTX)



# ── 預設常用清單（存在外掛資料夾的 defaults.json，會隨外掛一起發佈）──
# 找不到 json 時的內建後備值。
DEFAULT_SEED = {
    'mesh': "MIRROR,BEVEL,SOLIDIFY,SHRINKWRAP,SUBSURF,",
    'curve': "",
    'lattice': "",
    'gpencil': "",
}
DEFAULTS = dict(DEFAULT_SEED)


def _defaults_path():
    return os.path.join(os.path.dirname(__file__), "defaults.json")


def _load_defaults():
    global DEFAULTS
    merged = dict(DEFAULT_SEED)
    try:
        with open(_defaults_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        for k in merged:
            if isinstance(data.get(k), str):
                merged[k] = data[k]
    except Exception:
        pass
    DEFAULTS = merged


def _save_defaults():
    try:
        with open(_defaults_path(), "w", encoding="utf-8") as f:
            json.dump(DEFAULTS, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ── 常用清單（工作用，存在使用者偏好；就是介面上那排按鈕）──
def _prefs():
    return bpy.context.preferences.addons[__name__].preferences


def _working_get(prefs, base):
    return getattr(prefs, base + '_modifiers', "")


def _working_set_list(prefs, base, items):
    setattr(prefs, base + '_modifiers', (','.join(items) + ',') if items else "")


def _redraw_all():
    wm = bpy.context.window_manager
    if not wm:
        return
    for win in wm.windows:
        for area in win.screen.areas:
            area.tag_redraw()


class FavoriteModifiersAddonPreferences(AddonPreferences):
    bl_idname = __name__

    curve_modifiers: StringProperty(default="")
    lattice_modifiers: StringProperty(default="")
    gpencil_modifiers: StringProperty(default="")
    mesh_modifiers: StringProperty(default="")

    # 是否已把出貨預設種入（只做一次，不覆蓋使用者既有清單）
    seeded: BoolProperty(default=False)

    display_style_items = [
        ("BUTTONS", "Icon + Name", "", 1),
        ("ICONS", "Icon", "", 2),
    ]

    display_style: EnumProperty(
        name="Display Style", translation_context=I18N_CTX,
        items=display_style_items,
        default="ICONS"
    )

    edit_type: EnumProperty(
        name="Object Type", translation_context=I18N_CTX,
        items=[
            ('mesh', "Mesh", ""),
            ('curve', "Curve / Text / Surface", ""),
            ('lattice', "Lattice", ""),
            ('gpencil', "Grease Pencil", ""),
        ],
        default='mesh',
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "display_style")

        box = layout.box()
        box.prop(self, "edit_type")

        base = self.edit_type
        cur = [x for x in getattr(self, base + '_modifiers', "").split(',') if x]

        lst = box.column(align=True)
        if not cur:
            lst.label(text=_t("(No favorite modifiers yet - start from 'Add Modifier' below)"), text_ctxt=I18N_CTX)
        for ident in cur:
            mod = find(lambda m: m.identifier == ident, modifiers)
            row = lst.row(align=True)
            if mod:
                row.label(text=mod.name, icon=mod.icon)
            else:
                row.label(text=ident, icon='QUESTION')
            up = row.operator("object.fav_panel_move", text="", icon='TRIA_UP')
            up.mod_type = ident
            up.direction = 'UP'
            dn = row.operator("object.fav_panel_move", text="", icon='TRIA_DOWN')
            dn.mod_type = ident
            dn.direction = 'DOWN'
            xop = row.operator("object.fav_panel_remove", text="", icon='X')
            xop.mod_type = ident

        box.operator_menu_enum("object.fav_panel_add", "mod_type",
                               text=_t("Add Modifier"), text_ctxt=I18N_CTX, icon='ADD')

        row = box.row(align=True)
        row.operator("object.fav_set_default", text=_t("Save as Default"), text_ctxt=I18N_CTX, icon='PINNED')
        row.operator("object.fav_restore_default", text=_t("Restore Default"), text_ctxt=I18N_CTX, icon='LOOP_BACK')
        row.operator("object.fav_clear", text=_t("Clear"), text_ctxt=I18N_CTX, icon='TRASH')


def get_favorite_modifiers(context):
    ob_type = context.active_object.type
    addon_prefs = context.preferences.addons[__name__].preferences

    if ob_type in 'CURVE FONT SURFACE':
        ob_type = 'CURVE'
    elif ob_type == 'GREASEPENCIL':
        return addon_prefs.gpencil_modifiers

    return getattr(addon_prefs, ob_type.lower() + '_modifiers')


def set_favorite_modifiers(context, value):
    ob_type = context.active_object.type
    addon_prefs = context.preferences.addons[__name__].preferences

    if ob_type in 'CURVE FONT SURFACE':
        ob_type = 'CURVE'
    elif ob_type == 'GREASEPENCIL':
        addon_prefs.gpencil_modifiers = value
        return

    setattr(addon_prefs, ob_type.lower() + '_modifiers', value)


def _type_base(context):
    """目前物件對應的鍵：mesh / curve / lattice / gpencil。"""
    ob_type = context.active_object.type
    if ob_type in 'CURVE FONT SURFACE':
        return 'curve'
    if ob_type == 'GREASEPENCIL':
        return 'gpencil'
    return ob_type.lower()


def get_default_modifiers(context):
    return DEFAULTS.get(_type_base(context), "")


# 依物件類型分類的修改器與 enum 快取（快取避免 EnumProperty 字串被回收）
_mesh_mods = []
_gpencil_mods = []
_enum_by_base = {'mesh': [], 'curve': [], 'lattice': [], 'gpencil': []}

# 曲線／文字／曲面 可用的修改器（Blender 支援的子集）
CURVE_OK = {
    'ARRAY', 'BEVEL', 'BUILD', 'MIRROR', 'SCREW', 'SOLIDIFY', 'WELD',
    'ARMATURE', 'CAST', 'CURVE', 'HOOK', 'LATTICE', 'MESH_DEFORM',
    'SHRINKWRAP', 'SIMPLE_DEFORM', 'SMOOTH', 'WARP', 'WAVE',
}
# 晶格 可用的修改器（只有少數形變類）
LATTICE_OK = {
    'ARMATURE', 'CAST', 'CURVE', 'DISPLACE', 'HOOK', 'LATTICE',
    'MESH_DEFORM', 'SHRINKWRAP', 'SIMPLE_DEFORM', 'WARP', 'WAVE',
}


def _applicable(base):
    if base == 'gpencil':
        return _gpencil_mods
    if base == 'curve':
        return [m for m in _mesh_mods if m.identifier in CURVE_OK]
    if base == 'lattice':
        return [m for m in _mesh_mods if m.identifier in LATTICE_OK]
    return _mesh_mods  # mesh 與其他


def _rebuild_enums():
    for base in ('mesh', 'curve', 'lattice', 'gpencil'):
        items = []
        for i, m in enumerate(_applicable(base)):
            items.append((m.identifier, m.name, "", m.icon, i))
        _enum_by_base[base] = items


def _mod_items_active(self, context):
    # 依「目前作用中物件」的類型過濾
    if context.active_object is None:
        return _enum_by_base['mesh']
    return _enum_by_base.get(_type_base(context), _enum_by_base['mesh'])


def _mod_items_edit(self, context):
    # 依偏好面板「物件類型」下拉過濾
    prefs = context.preferences.addons[__name__].preferences
    return _enum_by_base.get(prefs.edit_type, _enum_by_base['mesh'])


class MODIFIER_OT_append_to_favorites(Operator):
    """Add to Favorite Modifiers list (stored in User Preferences)"""
    bl_idname = "object.append_to_favorites"
    bl_label = "Add to Favorite Modifiers"
    bl_translation_context = I18N_CTX

    mod_type: StringProperty()

    @classmethod
    def poll(cls, context):
        return context.object is not None

    def execute(self, context):
        fm = get_favorite_modifiers(context)
        set_favorite_modifiers(context, fm + self.mod_type + ',')
        context.area.tag_redraw()
        return {'FINISHED'}


class MODIFIER_OT_remove_from_favorites(Operator):
    """Remove from Favorite Modifiers list (stored in User Preferences)"""
    bl_idname = "object.remove_from_favorites"
    bl_label = "Remove from Favorite Modifiers"
    bl_translation_context = I18N_CTX

    mod_type: StringProperty()

    @classmethod
    def poll(cls, context):
        return context.object is not None

    def execute(self, context):
        fm = get_favorite_modifiers(context)
        set_favorite_modifiers(context, fm.replace(self.mod_type + ',', ''))
        context.area.tag_redraw()
        return {'FINISHED'}


class MODIFIER_OT_add_favorite_modifier(Operator):
    """Add a procedural operation/effect to the active object"""
    bl_idname = "object.add_favorite_modifier"
    bl_label = "Add Favorite Modifier"
    bl_translation_context = I18N_CTX

    mod_type: StringProperty()

    @classmethod
    def description(cls, context, properties):
        # 讓每顆按鈕的 tooltip 顯示該修改器自己的名稱與說明
        mod = find(lambda m: m.identifier == properties.mod_type, modifiers)
        if mod:
            if getattr(mod, 'description', ""):
                return mod.name + "：" + mod.description
            return mod.name
        return "新增常用修改器"

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        active_object_type = context.active_object.type

        if active_object_type == 'GPENCIL':
            bpy.ops.object.gpencil_modifier_add(type=self.mod_type)
        else:
            bpy.ops.object.modifier_add(type=self.mod_type)
        return {'FINISHED'}


class MODIFIER_OT_add_favorite_via_search(Operator):
    """搜尋並加入常用修改器（常用列末端的「＋」）"""
    bl_idname = "object.add_favorite_search"
    bl_label = "Add Favorite Modifier by Search"
    bl_translation_context = I18N_CTX
    bl_property = "mod_type"

    mod_type: EnumProperty(items=_mod_items_active)

    @classmethod
    def poll(cls, context):
        return context.object is not None

    def execute(self, context):
        items = [x for x in get_favorite_modifiers(context).split(',') if x]
        if self.mod_type not in items:
            items.append(self.mod_type)
            set_favorite_modifiers(context, ','.join(items) + ',')
        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {'FINISHED'}


class MODIFIER_OT_move_favorite(Operator):
    """在常用清單中左移/右移這個修改器（右鍵選單用）"""
    bl_idname = "object.move_favorite_modifier"
    bl_label = "Move Favorite Modifier"
    bl_translation_context = I18N_CTX

    mod_type: StringProperty()
    direction: StringProperty()  # 'UP'（左移）或 'DOWN'（右移）

    @classmethod
    def poll(cls, context):
        return context.object is not None

    def execute(self, context):
        items = [x for x in get_favorite_modifiers(context).split(',') if x]
        if self.mod_type in items:
            i = items.index(self.mod_type)
            j = i - 1 if self.direction == 'UP' else i + 1
            if 0 <= j < len(items):
                items[i], items[j] = items[j], items[i]
                set_favorite_modifiers(context, ','.join(items) + ',')
        context.area.tag_redraw()
        return {'FINISHED'}


# ── 面板編輯用（依偏好面板的「物件類型」下拉，直接編輯該類型的工作清單）──
class MODIFIER_OT_panel_add(Operator):
    """把修改器加入目前選定物件類型的常用清單"""
    bl_idname = "object.fav_panel_add"
    bl_label = "Add Modifier"
    bl_translation_context = I18N_CTX

    mod_type: EnumProperty(items=_mod_items_edit)

    def execute(self, context):
        prefs = _prefs()
        base = prefs.edit_type
        items = [x for x in _working_get(prefs, base).split(',') if x]
        if self.mod_type not in items:
            items.append(self.mod_type)
            _working_set_list(prefs, base, items)
            _redraw_all()
        return {'FINISHED'}


class MODIFIER_OT_panel_remove(Operator):
    """從目前選定物件類型的常用清單移除修改器"""
    bl_idname = "object.fav_panel_remove"
    bl_label = "Remove"
    bl_translation_context = I18N_CTX

    mod_type: StringProperty()

    def execute(self, context):
        prefs = _prefs()
        base = prefs.edit_type
        items = [x for x in _working_get(prefs, base).split(',') if x and x != self.mod_type]
        _working_set_list(prefs, base, items)
        _redraw_all()
        return {'FINISHED'}


class MODIFIER_OT_panel_move(Operator):
    """在常用清單中上移/下移修改器（面板用）"""
    bl_idname = "object.fav_panel_move"
    bl_label = "Move"
    bl_translation_context = I18N_CTX

    mod_type: StringProperty()
    direction: StringProperty()

    def execute(self, context):
        prefs = _prefs()
        base = prefs.edit_type
        items = [x for x in _working_get(prefs, base).split(',') if x]
        if self.mod_type in items:
            i = items.index(self.mod_type)
            j = i - 1 if self.direction == 'UP' else i + 1
            if 0 <= j < len(items):
                items[i], items[j] = items[j], items[i]
                _working_set_list(prefs, base, items)
                _redraw_all()
        return {'FINISHED'}


class MODIFIER_OT_fav_set_default(Operator):
    """把目前清單存成預設（會寫入 defaults.json，隨外掛發佈）"""
    bl_idname = "object.fav_set_default"
    bl_label = "Save as Default"
    bl_translation_context = I18N_CTX

    def execute(self, context):
        prefs = _prefs()
        base = prefs.edit_type
        DEFAULTS[base] = _working_get(prefs, base)
        _save_defaults()
        self.report({'INFO'}, _t("Saved as default"))
        return {'FINISHED'}


class MODIFIER_OT_fav_restore_default(Operator):
    """把目前清單恢復成預設"""
    bl_idname = "object.fav_restore_default"
    bl_label = "Restore Default"
    bl_translation_context = I18N_CTX

    def execute(self, context):
        prefs = _prefs()
        base = prefs.edit_type
        items = [x for x in DEFAULTS.get(base, "").split(',') if x]
        _working_set_list(prefs, base, items)
        _redraw_all()
        self.report({'INFO'}, _t("Restored to default"))
        return {'FINISHED'}


class MODIFIER_OT_fav_clear(Operator):
    """清空目前物件類型的常用清單"""
    bl_idname = "object.fav_clear"
    bl_label = "Clear"
    bl_translation_context = I18N_CTX

    def execute(self, context):
        prefs = _prefs()
        _working_set_list(prefs, prefs.edit_type, [])
        _redraw_all()
        return {'FINISHED'}


class WM_MT_button_context(Menu):
    bl_label = "Add / Remove Favorite Modifier"
    bl_translation_context = I18N_CTX

    def draw(self, context):
        if not hasattr(context, 'button_operator'):
            return
        if not hasattr(context.space_data, 'context'):
            return
        if context.space_data.context != 'MODIFIER':
            return

        op = context.button_operator

        if "modifier_add" in str(getattr(op, 'bl_rna')):
            mod_type = getattr(op, 'type')
            layout = self.layout
            layout.separator()
            if mod_type not in get_favorite_modifiers(context):
                layout.operator("object.append_to_favorites",
                                text=_t("Add to Favorite Modifiers"), text_ctxt=I18N_CTX,
                                icon='SOLO_ON').mod_type = mod_type
            else:
                layout.operator("object.remove_from_favorites",
                                text=_t("Remove from Favorite Modifiers"), text_ctxt=I18N_CTX,
                                icon='SOLO_ON').mod_type = mod_type
            layout.separator()
        elif "favadd_" in str(getattr(op, 'bl_rna')):
            mod_type = getattr(op, 'mod_type', "")
            layout = self.layout
            layout.separator()
            lop = layout.operator("object.move_favorite_modifier",
                                  text=_t("Move Button Left"), text_ctxt=I18N_CTX, icon='TRIA_LEFT')
            lop.mod_type = mod_type
            lop.direction = 'UP'
            rop = layout.operator("object.move_favorite_modifier",
                                  text=_t("Move Button Right"), text_ctxt=I18N_CTX, icon='TRIA_RIGHT')
            rop.mod_type = mod_type
            rop.direction = 'DOWN'
            layout.operator("object.remove_from_favorites",
                            text=_t("Remove from Favorite Modifiers"), text_ctxt=I18N_CTX,
                            icon='SOLO_ON').mod_type = mod_type
            layout.separator()


def find(f, seq):
    for item in seq:
        if f(item):
            return item

    return None


# ── 每個修改器各自一顆「加入」operator ──
# 用 bl_label=修改器名、bl_description=修改器說明；Blender 會照使用者語系自動翻譯，
# 於是 tooltip 標題會顯示（翻譯後的）修改器名，說明也跟著語系走。
_dynamic_add_classes = []


def _add_op_idname(identifier):
    return "object.favadd_" + identifier.lower()


def _make_add_op(identifier, name, description):
    def execute(self, context):
        ob = context.active_object
        try:
            if ob and ob.type == 'GPENCIL':
                bpy.ops.object.gpencil_modifier_add(type=identifier)
            else:
                bpy.ops.object.modifier_add(type=identifier)
        except Exception:
            self.report({'WARNING'}, _t('"%s" does not apply to the current object type') % name)
            return {'CANCELLED'}
        return {'FINISHED'}

    return type(
        "MODIFIER_OT_favadd_" + identifier.lower(),
        (Operator,),
        {
            "bl_idname": _add_op_idname(identifier),
            "bl_label": name,
            "bl_description": description if description else name,
            "__annotations__": {"mod_type": StringProperty(default=identifier)},
            "execute": execute,
            "poll": classmethod(lambda cls, ctx: ctx.active_object is not None),
        },
    )


def draw_favorite_modifiers(self, context):
    if context.active_object is None:
        return

    mods = []
    fms = get_favorite_modifiers(context)[:-1].split(',')

    for mod_type in fms:
        mod = find(lambda mod: mod.identifier == mod_type, modifiers)
        if mod:
            mods.append(mod)

    layout = self.layout

    # 空狀態引導：沒有任何常用時，提示 + 一顆「＋」
    if len(mods) == 0:
        row = layout.row(align=True)
        row.label(text=_t("Press + to add a favorite modifier"), text_ctxt=I18N_CTX, icon='INFO')
        row.operator("object.add_favorite_search", text="", icon='ADD')
        return

    addon_prefs = context.preferences.addons[__name__].preferences
    display_style = addon_prefs.display_style

    if display_style == 'BUTTONS':
        grid_flow = layout.grid_flow(
            row_major=True, columns=4,
            even_columns=True, even_rows=True,
            align=True)
        grid_flow.scale_x = 0.8

        for mod in mods:
            grid_flow.operator(_add_op_idname(mod.identifier),
                               text=mod.name, icon=mod.icon)
    elif display_style == 'ICONS':
        grid_flow = layout.grid_flow(
            row_major=True, columns=0,
            even_columns=True, even_rows=True,
            align=True)
        grid_flow.scale_x = 1.0
        grid_flow.scale_y = 1.0

        for mod in mods:
            grid_flow.operator(_add_op_idname(mod.identifier),
                               text="", icon=mod.icon)


classes = (
    FavoriteModifiersAddonPreferences,
    MODIFIER_OT_append_to_favorites,
    MODIFIER_OT_remove_from_favorites,
    MODIFIER_OT_add_favorite_modifier,
    MODIFIER_OT_add_favorite_via_search,
    MODIFIER_OT_move_favorite,
    MODIFIER_OT_panel_add,
    MODIFIER_OT_panel_remove,
    MODIFIER_OT_panel_move,
    MODIFIER_OT_fav_set_default,
    MODIFIER_OT_fav_restore_default,
    MODIFIER_OT_fav_clear,
    WM_MT_button_context,
)


modifiers = []


def _seed_defaults():
    # 延遲執行：把預設種進「空的」清單（只做一次，不覆蓋既有內容）
    try:
        prefs = bpy.context.preferences.addons[__name__].preferences
    except Exception:
        return 0.1
    if not prefs.seeded:
        for base, val in DEFAULTS.items():
            attr = base + '_modifiers'
            if val and hasattr(prefs, attr) and getattr(prefs, attr) == "":
                setattr(prefs, attr, val)
        prefs.seeded = True
    return None


def register():
    bpy.app.translations.register(__name__, translations_dict)
    for cls in classes:
        register_class(cls)

    modifiers.clear()
    _mesh_mods.clear()
    _gpencil_mods.clear()
    for mod in Modifier.bl_rna.properties['type'].enum_items:
        modifiers.append(mod)
        _mesh_mods.append(mod)

    if hasattr(bpy.types, 'GpencilModifier'):
        for mod in bpy.types.GpencilModifier.bl_rna.properties['type'].enum_items:
            modifiers.append(mod)
            _gpencil_mods.append(mod)

    _rebuild_enums()

    # 為每個修改器註冊一顆「加入」operator（讓 tooltip 顯示各自的名稱／說明）
    _dynamic_add_classes.clear()
    seen = set()
    for mod in modifiers:
        if mod.identifier in seen:
            continue
        seen.add(mod.identifier)
        cls = _make_add_op(mod.identifier, mod.name, mod.description)
        try:
            register_class(cls)
            _dynamic_add_classes.append(cls)
        except Exception:
            pass

    _load_defaults()

    DATA_PT_modifiers.prepend(draw_favorite_modifiers)

    bpy.app.timers.register(_seed_defaults, first_interval=0.1)


def unregister():
    for cls in classes:
        unregister_class(cls)

    for cls in _dynamic_add_classes:
        try:
            unregister_class(cls)
        except Exception:
            pass
    _dynamic_add_classes.clear()

    DATA_PT_modifiers.remove(draw_favorite_modifiers)

    try:
        bpy.app.translations.unregister(__name__)
    except Exception:
        pass


if __name__ == "__main__":
    register()
