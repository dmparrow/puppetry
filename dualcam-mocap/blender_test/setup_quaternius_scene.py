from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy
from mathutils import Vector


DEFAULT_ACTORS = ["Warrior", "Wizard", "Ranger", "Monk"]
PREFERRED_EXTENSIONS = [".glb", ".gltf", ".fbx"]


def parse_args() -> argparse.Namespace:
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser(description="Build a four-actor Quaternius mocap test scene")
    parser.add_argument("--pack-dir", required=True, help="Extracted Quaternius RPG Character Pack directory")
    parser.add_argument("--output", default="mocap_four_actor_test.blend")
    parser.add_argument("--actors", nargs="*", default=DEFAULT_ACTORS)
    parser.add_argument("--spacing", type=float, default=2.0)
    return parser.parse_args(argv)


def clean_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in list(bpy.data.collections):
        if collection.users == 0:
            bpy.data.collections.remove(collection)


def find_character_file(pack_dir: Path, keyword: str) -> Path:
    candidates: list[Path] = []
    needle = keyword.lower()
    for path in pack_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in PREFERRED_EXTENSIONS:
            continue
        lowered = path.stem.lower()
        if needle in lowered:
            candidates.append(path)

    if not candidates:
        raise FileNotFoundError(
            f"Could not find a {keyword!r} FBX/glTF/GLB under {pack_dir}. "
            "Pass different names with --actors if this pack uses different filenames."
        )

    extension_rank = {ext: i for i, ext in enumerate(PREFERRED_EXTENSIONS)}
    candidates.sort(key=lambda p: (extension_rank.get(p.suffix.lower(), 99), len(str(p))))
    return candidates[0]


def import_character(path: Path) -> list[bpy.types.Object]:
    before = set(bpy.data.objects)
    suffix = path.suffix.lower()
    if suffix in {".glb", ".gltf"}:
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path), automatic_bone_orientation=False)
    else:
        raise ValueError(f"Unsupported import format: {path}")
    return [obj for obj in bpy.data.objects if obj not in before]


def clear_imported_animation(objects: list[bpy.types.Object]) -> None:
    for obj in objects:
        if obj.animation_data:
            obj.animation_data.action = None
            for track in list(obj.animation_data.nla_tracks):
                obj.animation_data.nla_tracks.remove(track)
        if obj.type == "ARMATURE":
            obj.data.pose_position = "POSE"


def add_actor_root(objects: list[bpy.types.Object], actor_id: int, label: str, location: Vector):
    root = bpy.data.objects.new(f"MOCAP_TEST_ACTOR_{actor_id}_{label}", None)
    bpy.context.scene.collection.objects.link(root)
    root.location = location
    root["mocap_actor_id"] = actor_id
    root["mocap_label"] = label
    root["mocap_test_actor"] = True

    imported = set(objects)
    for obj in objects:
        if obj.parent is None or obj.parent not in imported:
            world = obj.matrix_world.copy()
            obj.parent = root
            obj.matrix_world = world

    armatures = [obj for obj in objects if obj.type == "ARMATURE"]
    if not armatures:
        raise RuntimeError(f"Imported {label} but found no armature")

    armature = max(armatures, key=lambda obj: len(obj.data.bones))
    armature.name = f"MOCAP_ACTOR_{actor_id}_{label}_ARMATURE"
    armature["mocap_actor_id"] = actor_id
    armature["mocap_label"] = label
    armature["mocap_test_actor"] = True
    return root, armature


def add_label(actor_id: int, label: str, location: Vector) -> None:
    curve = bpy.data.curves.new(f"Actor_{actor_id}_Label", type="FONT")
    curve.body = f"Actor {actor_id} — {label}"
    curve.align_x = "CENTER"
    curve.size = 0.3
    text = bpy.data.objects.new(f"Actor_{actor_id}_Label", curve)
    bpy.context.scene.collection.objects.link(text)
    text.location = location + Vector((0.0, 0.0, 2.4))
    text.rotation_euler = (1.57079632679, 0.0, 0.0)


def add_floor(width: float) -> None:
    bpy.ops.mesh.primitive_plane_add(size=max(10.0, width))
    floor = bpy.context.active_object
    floor.name = "MOCAP_TEST_FLOOR"
    floor.location.z = 0.0


def main() -> None:
    args = parse_args()
    pack_dir = Path(args.pack_dir).expanduser().resolve()
    if not pack_dir.exists():
        raise FileNotFoundError(pack_dir)

    actors = args.actors[:4]
    if len(actors) < 4:
        raise ValueError("Provide four actor names")

    clean_scene()
    bpy.context.scene.render.fps = 30

    centre = (len(actors) - 1) * args.spacing * 0.5
    summary = []

    for index, label in enumerate(actors, start=1):
        source = find_character_file(pack_dir, label)
        print(f"Actor {index}: importing {label} from {source}")
        imported = import_character(source)
        clear_imported_animation(imported)
        offset = Vector(((index - 1) * args.spacing - centre, 0.0, 0.0))
        _, armature = add_actor_root(imported, index, label, offset)
        add_label(index, label, offset)
        summary.append((index, label, armature.name, source))

    add_floor((len(actors) + 1) * args.spacing)

    scene = bpy.context.scene
    scene["mocap_test_scene"] = True
    scene["mocap_actor_count"] = len(actors)
    scene["mocap_test_source"] = "Quaternius RPG Character Pack (CC0)"

    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))

    print("\nFour-actor mocap test scene created:")
    for actor_id, label, armature, source in summary:
        print(f"  Actor {actor_id}: {label:8s} -> {armature} ({source.name})")
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
