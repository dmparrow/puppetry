from __future__ import annotations

bl_info = {
    "name": "DualCam Live Mocap",
    "author": "dmparrow + OpenAI",
    "version": (0, 1, 0),
    "blender": (4, 3, 0),
    "location": "View3D > Sidebar > Mocap",
    "description": "Receive a live triangulated skeleton and drive a Blender armature",
    "category": "Animation",
}

import json
import socket
import threading
from typing import Optional

import bpy
from mathutils import Matrix, Vector

_lock = threading.Lock()
_latest: Optional[dict] = None
_reader_thread: Optional[threading.Thread] = None
_stop = threading.Event()
_sock: Optional[socket.socket] = None
_driver_rest: dict[str, Matrix] = {}
_target_armature_name: Optional[str] = None
_last_applied_seq = -1

TARGET_BONES = {
    "spine": ["spine_fk.001", "spine_fk", "DEF-spine.001", "spine", "mixamorig:Spine"],
    "upper_arm.L": ["upper_arm_fk.L", "DEF-upper_arm.L", "upper_arm.L", "mixamorig:LeftArm"],
    "forearm.L": ["forearm_fk.L", "DEF-forearm.L", "forearm.L", "mixamorig:LeftForeArm"],
    "upper_arm.R": ["upper_arm_fk.R", "DEF-upper_arm.R", "upper_arm.R", "mixamorig:RightArm"],
    "forearm.R": ["forearm_fk.R", "DEF-forearm.R", "forearm.R", "mixamorig:RightForeArm"],
    "thigh.L": ["thigh_fk.L", "DEF-thigh.L", "thigh.L", "mixamorig:LeftUpLeg"],
    "shin.L": ["shin_fk.L", "DEF-shin.L", "shin.L", "mixamorig:LeftLeg"],
    "thigh.R": ["thigh_fk.R", "DEF-thigh.R", "thigh.R", "mixamorig:RightUpLeg"],
    "shin.R": ["shin_fk.R", "DEF-shin.R", "shin.R", "mixamorig:RightLeg"],
}

SEGMENTS = {
    "spine": ("hips_center", "shoulders_center"),
    "upper_arm.L": ("left_shoulder", "left_elbow"),
    "forearm.L": ("left_elbow", "left_wrist"),
    "upper_arm.R": ("right_shoulder", "right_elbow"),
    "forearm.R": ("right_elbow", "right_wrist"),
    "thigh.L": ("left_hip", "left_knee"),
    "shin.L": ("left_knee", "left_ankle"),
    "thigh.R": ("right_hip", "right_knee"),
    "shin.R": ("right_knee", "right_ankle"),
}


def _scene_props():
    return bpy.context.scene.dualcam_mocap


def _cv_to_blender(xyz) -> Vector:
    p = Vector((float(xyz[0]), float(xyz[1]), float(xyz[2])))
    scale = float(_scene_props().world_scale)
    return Vector((p.x, p.z, -p.y)) * scale


def _expanded_points(payload: dict) -> dict[str, Vector]:
    raw = payload.get("points", {})
    points = {
        name: _cv_to_blender(value["xyz"])
        for name, value in raw.items()
        if isinstance(value, dict) and "xyz" in value
    }
    if "left_hip" in points and "right_hip" in points:
        points["hips_center"] = (points["left_hip"] + points["right_hip"]) * 0.5
    if "left_shoulder" in points and "right_shoulder" in points:
        points["shoulders_center"] = (points["left_shoulder"] + points["right_shoulder"]) * 0.5
    return points


def _reader(host: str, port: int) -> None:
    global _latest, _sock
    try:
        sock = socket.create_connection((host, port), timeout=4.0)
        sock.settimeout(1.0)
        _sock = sock
        buffer = b""
        while not _stop.is_set():
            try:
                chunk = sock.recv(65536)
            except socket.timeout:
                continue
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                if not line:
                    continue
                try:
                    payload = json.loads(line.decode("utf-8"))
                except Exception:
                    continue
                if payload.get("type") == "skeleton":
                    with _lock:
                        _latest = payload
    except Exception as exc:
        print(f"[DualCam Mocap] connection ended: {exc}")
    finally:
        try:
            if _sock:
                _sock.close()
        except Exception:
            pass
        _sock = None


def _start_reader(host: str, port: int) -> None:
    global _reader_thread
    _stop.clear()
    _reader_thread = threading.Thread(target=_reader, args=(host, port), daemon=True)
    _reader_thread.start()


def _stop_reader() -> None:
    _stop.set()
    global _sock
    try:
        if _sock:
            _sock.shutdown(socket.SHUT_RDWR)
            _sock.close()
    except Exception:
        pass
    _sock = None


def _ensure_empty(name: str):
    object_name = f"MOCAP_{name}"
    obj = bpy.data.objects.get(object_name)
    if obj is None:
        obj = bpy.data.objects.new(object_name, None)
        obj.empty_display_type = "SPHERE"
        obj.empty_display_size = 0.025
        bpy.context.collection.objects.link(obj)
    return obj


def _update_debug_points(points: dict[str, Vector]) -> None:
    if not _scene_props().show_debug_points:
        return
    for name, pos in points.items():
        _ensure_empty(name).location = pos


def _basis_from_direction(rest_matrix: Matrix, rest_head: Vector, rest_tail: Vector, target_dir: Vector) -> Matrix:
    rest_dir = (rest_tail - rest_head).normalized()
    target_dir = target_dir.normalized()
    q = rest_dir.rotation_difference(target_dir)
    rot = q.to_matrix() @ rest_matrix.to_3x3()
    result = rot.to_4x4()
    result.translation = rest_matrix.translation
    return result


def _update_driver(points: dict[str, Vector], record: bool) -> None:
    rig = bpy.data.objects.get("MOCAP_DRIVER")
    if rig is None or rig.type != "ARMATURE":
        return
    for semantic, (head_name, tail_name) in SEGMENTS.items():
        pb = rig.pose.bones.get(semantic)
        if pb is None or head_name not in points or tail_name not in points:
            continue
        rest = _driver_rest.get(semantic, pb.bone.matrix_local.copy())
        head = points[head_name]
        tail = points[tail_name]
        direction = tail - head
        if direction.length < 1e-6:
            continue
        desired = _basis_from_direction(rest, pb.bone.head_local, pb.bone.tail_local, direction)
        desired.translation = head
        pb.matrix = desired
        if record:
            pb.rotation_mode = "QUATERNION"
            pb.keyframe_insert(data_path="location")
            pb.keyframe_insert(data_path="rotation_quaternion")


def _find_target_pose_bone(armature, semantic: str):
    for candidate in TARGET_BONES.get(semantic, []):
        pb = armature.pose.bones.get(candidate)
        if pb is not None:
            return pb
    return None


def _update_target_rig(points: dict[str, Vector], record: bool) -> None:
    if not _target_armature_name:
        return
    arm = bpy.data.objects.get(_target_armature_name)
    if arm is None or arm.type != "ARMATURE":
        return
    inv_world = arm.matrix_world.inverted()
    for semantic, (head_name, tail_name) in SEGMENTS.items():
        pb = _find_target_pose_bone(arm, semantic)
        if pb is None or head_name not in points or tail_name not in points:
            continue
        head_local = inv_world @ points[head_name]
        tail_local = inv_world @ points[tail_name]
        direction = tail_local - head_local
        if direction.length < 1e-6:
            continue
        rest = pb.bone.matrix_local.copy()
        desired = _basis_from_direction(rest, pb.bone.head_local, pb.bone.tail_local, direction)
        desired.translation = rest.translation
        pb.matrix = desired
        if record:
            pb.rotation_mode = "QUATERNION"
            pb.keyframe_insert(data_path="rotation_quaternion")


def _apply_latest():
    global _last_applied_seq
    try:
        with _lock:
            payload = dict(_latest) if _latest is not None else None
        if payload is None:
            return 1.0 / 30.0
        seq = int(payload.get("seq", -1))
        if seq == _last_applied_seq:
            return 1.0 / 60.0
        _last_applied_seq = seq
        points = _expanded_points(payload)
        _update_debug_points(points)
        record = bool(_scene_props().record)
        _update_driver(points, record)
        _update_target_rig(points, record)
    except Exception as exc:
        print(f"[DualCam Mocap] apply failed: {exc}")
    return 1.0 / 60.0


class DualCamMocapProperties(bpy.types.PropertyGroup):
    host: bpy.props.StringProperty(name="GPU Host", default="127.0.0.1")
    port: bpy.props.IntProperty(name="Port", default=8766, min=1, max=65535)
    world_scale: bpy.props.FloatProperty(name="World Scale", default=1.0, min=0.001, max=1000.0)
    show_debug_points: bpy.props.BoolProperty(name="Debug Points", default=True)
    record: bpy.props.BoolProperty(name="Record", default=False)


class DUALCAM_OT_connect(bpy.types.Operator):
    bl_idname = "dualcam.connect"
    bl_label = "Connect"
    def execute(self, context):
        props = context.scene.dualcam_mocap
        _stop_reader()
        _start_reader(props.host, props.port)
        self.report({'INFO'}, f"Connecting to {props.host}:{props.port}")
        return {'FINISHED'}


class DUALCAM_OT_disconnect(bpy.types.Operator):
    bl_idname = "dualcam.disconnect"
    bl_label = "Disconnect"
    def execute(self, context):
        _stop_reader()
        return {'FINISHED'}


class DUALCAM_OT_create_driver(bpy.types.Operator):
    bl_idname = "dualcam.create_driver"
    bl_label = "Create Driver Rig"
    def execute(self, context):
        global _driver_rest
        with _lock:
            payload = dict(_latest) if _latest is not None else None
        if not payload:
            self.report({'ERROR'}, "No skeleton frame received yet")
            return {'CANCELLED'}
        points = _expanded_points(payload)
        existing = bpy.data.objects.get("MOCAP_DRIVER")
        if existing:
            bpy.data.objects.remove(existing, do_unlink=True)
        arm_data = bpy.data.armatures.new("MOCAP_DRIVER_DATA")
        arm_obj = bpy.data.objects.new("MOCAP_DRIVER", arm_data)
        context.collection.objects.link(arm_obj)
        context.view_layer.objects.active = arm_obj
        arm_obj.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')
        made = 0
        for semantic, (head_name, tail_name) in SEGMENTS.items():
            if head_name not in points or tail_name not in points:
                continue
            head, tail = points[head_name], points[tail_name]
            if (tail - head).length < 1e-5:
                continue
            bone = arm_data.edit_bones.new(semantic)
            bone.head = head
            bone.tail = tail
            made += 1
        bpy.ops.object.mode_set(mode='POSE')
        _driver_rest = {pb.name: pb.bone.matrix_local.copy() for pb in arm_obj.pose.bones}
        bpy.ops.object.mode_set(mode='OBJECT')
        self.report({'INFO'}, f"Created MOCAP_DRIVER with {made} bones")
        return {'FINISHED'}


class DUALCAM_OT_bind_selected(bpy.types.Operator):
    bl_idname = "dualcam.bind_selected"
    bl_label = "Bind Selected Rig"
    def execute(self, context):
        global _target_armature_name
        obj = context.active_object
        if obj is None or obj.type != "ARMATURE":
            self.report({'ERROR'}, "Select an armature first")
            return {'CANCELLED'}
        _target_armature_name = obj.name
        matched = sum(1 for key in SEGMENTS if _find_target_pose_bone(obj, key))
        self.report({'INFO'}, f"Bound {obj.name}: {matched}/{len(SEGMENTS)} segments mapped")
        return {'FINISHED'}


class DUALCAM_OT_unbind(bpy.types.Operator):
    bl_idname = "dualcam.unbind"
    bl_label = "Unbind"
    def execute(self, context):
        global _target_armature_name
        _target_armature_name = None
        return {'FINISHED'}


class DUALCAM_PT_panel(bpy.types.Panel):
    bl_label = "DualCam Mocap"
    bl_idname = "DUALCAM_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Mocap'
    def draw(self, context):
        layout = self.layout
        props = context.scene.dualcam_mocap
        col = layout.column(align=True)
        col.prop(props, "host")
        col.prop(props, "port")
        row = col.row(align=True)
        row.operator("dualcam.connect", icon='LINKED')
        row.operator("dualcam.disconnect", icon='UNLINKED')
        col.separator()
        col.prop(props, "world_scale")
        col.prop(props, "show_debug_points")
        col.operator("dualcam.create_driver", icon='ARMATURE_DATA')
        col.separator()
        col.operator("dualcam.bind_selected", icon='CONSTRAINT_BONE')
        col.operator("dualcam.unbind")
        col.prop(props, "record", toggle=True, icon='REC')


_CLASSES = (
    DualCamMocapProperties,
    DUALCAM_OT_connect,
    DUALCAM_OT_disconnect,
    DUALCAM_OT_create_driver,
    DUALCAM_OT_bind_selected,
    DUALCAM_OT_unbind,
    DUALCAM_PT_panel,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.dualcam_mocap = bpy.props.PointerProperty(type=DualCamMocapProperties)
    if not bpy.app.timers.is_registered(_apply_latest):
        bpy.app.timers.register(_apply_latest, first_interval=0.1, persistent=True)


def unregister():
    _stop_reader()
    if bpy.app.timers.is_registered(_apply_latest):
        bpy.app.timers.unregister(_apply_latest)
    del bpy.types.Scene.dualcam_mocap
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
