"""Scene construction and numeric parameter helpers."""
from __future__ import annotations

import copy
import math
from typing import Any, Dict, List, Sequence

from .math3d import Camera, Light, Material, Vec3, vec3_from

def default_material() -> Dict[str, Any]:
    return {
        "color": [0.8, 0.8, 0.8],
        "roughness": 0.4,
        "metallic": 0.0,
        "reflectivity": 0.0,
        "emission": [0.0, 0.0, 0.0],
    }

def make_sphere_node(node_id: str, center: Sequence[float], radius: float, material: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": node_id, "kind": "sphere", "params": {"center": list(center), "radius": radius}, "material": material}

def make_box_node(node_id: str, center: Sequence[float], half_size: Sequence[float], rotation_y: float, material: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": node_id,
        "kind": "box",
        "params": {"center": list(center), "half_size": list(half_size), "rotation_y": rotation_y},
        "material": material,
    }

def sample_scene() -> Dict[str, Any]:
    coral = {"color": [0.93, 0.34, 0.28], "roughness": 0.23, "metallic": 0.02, "reflectivity": 0.18, "emission": [0.0, 0.0, 0.0]}
    gold = {"color": [0.96, 0.83, 0.27], "roughness": 0.16, "metallic": 0.88, "reflectivity": 0.30, "emission": [0.0, 0.0, 0.0]}
    blue = {"color": [0.25, 0.56, 0.97], "roughness": 0.21, "metallic": 0.10, "reflectivity": 0.22, "emission": [0.0, 0.0, 0.0]}
    glow = {"color": [0.7, 0.92, 1.0], "roughness": 1.0, "metallic": 0.0, "reflectivity": 0.0, "emission": [0.38, 0.44, 0.58]}
    return {
        "camera": {"origin": [0.0, 0.24, -5.4], "target": [0.0, 0.1, 4.7], "up": [0.0, 1.0, 0.0], "fov_degrees": 50.0},
        "lights": [
            {"id": "key", "position": [4.0, 6.0, -3.2], "color": [1.0, 0.96, 0.92], "intensity": 1.8},
            {"id": "rim", "position": [-5.8, 3.4, 2.1], "color": [0.42, 0.60, 1.0], "intensity": 0.52},
        ],
        "objects": [
            {"id": "ground", "kind": "plane", "params": {"normal": [0.0, 1.0, 0.0], "offset": 0.95}, "material": {"color": [0.76, 0.79, 0.83], "roughness": 0.98, "metallic": 0.0, "reflectivity": 0.02, "emission": [0.0, 0.0, 0.0]}},
            {"id": "hero_blob", "kind": "smooth_union", "params": {"k": 0.48}, "children": [make_sphere_node("hero_blob_a", [-0.42, -0.02, 4.35], 0.76, coral), make_sphere_node("hero_blob_b", [0.36, 0.08, 4.52], 0.70, coral)]},
            {"id": "carved_box", "kind": "subtract", "children": [make_box_node("carved_box_base", [1.85, -0.12, 5.42], [0.62, 0.62, 0.62], 0.34, gold), make_sphere_node("carved_box_cut", [1.60, 0.08, 5.10], 0.52, gold)]},
            {"id": "blue_intersection", "kind": "intersection", "children": [make_sphere_node("blue_intersection_sphere", [-1.70, -0.10, 5.20], 0.82, blue), make_box_node("blue_intersection_box", [-1.52, -0.06, 5.18], [0.58, 0.58, 0.58], -0.28, blue)]},
            make_sphere_node("glow_ball", [0.0, 1.02, 3.08], 0.26, glow),
        ],
    }

def clone_scene(scene: Dict[str, Any]) -> Dict[str, Any]:
    return copy.deepcopy(scene)

def build_sample_clip(num_frames: int, fps: int) -> List[Dict[str, Any]]:
    base = sample_scene()
    frames: List[Dict[str, Any]] = []
    dt = 1.0 / fps
    for i in range(num_frames):
        t = i * dt
        scene = clone_scene(base)
        cam = scene["camera"]
        cam["origin"][0] = 0.28 * math.sin(t * 0.7)
        cam["origin"][1] = 0.22 + 0.07 * math.sin(t * 0.9)
        cam["target"][0] = 0.16 * math.sin(t * 0.55)
        hero_children = scene["objects"][1]["children"]
        hero_children[0]["params"]["center"][0] = -0.42 + 0.55 * t - 0.08 * t * t
        hero_children[0]["params"]["center"][1] = -0.02 + 0.10 * math.sin(t * 1.7)
        hero_children[1]["params"]["center"][0] = 0.36 + 0.28 * math.sin(t * 1.1)
        hero_children[1]["params"]["center"][1] = 0.08 + 0.14 * math.sin(t * 2.0)
        scene["objects"][1]["params"]["k"] = 0.48 + 0.08 * math.sin(t * 1.3)
        carved_box = scene["objects"][2]
        carved_box["children"][0]["params"]["rotation_y"] = 0.34 + 0.44 * math.sin(t * 1.4)
        carved_box["children"][1]["params"]["center"][1] = 0.08 + 0.15 * math.sin(t * 1.6)
        blue_intersection = scene["objects"][3]
        blue_intersection["children"][1]["params"]["rotation_y"] = -0.28 + 0.55 * math.sin(t * 0.9)
        blue_intersection["children"][0]["params"]["center"][1] = -0.10 + 0.11 * math.sin(t * 1.1)
        scene["objects"][4]["params"]["center"][0] = 0.18 * math.cos(t * 1.5)
        scene["objects"][4]["params"]["center"][1] = 1.02 + 0.12 * math.sin(t * 2.1)
        scene["lights"][0]["position"][0] = 4.0 + 0.25 * t
        scene["lights"][1]["position"][2] = 2.1 + 0.35 * math.sin(t * 0.8)
        frames.append(scene)
    return frames

def material_from_dict(d: Dict[str, Any]) -> Material:
    md = default_material()
    md.update(d or {})
    return Material(color=vec3_from(md["color"]), roughness=float(md.get("roughness", 0.4)), metallic=float(md.get("metallic", 0.0)), reflectivity=float(md.get("reflectivity", 0.0)), emission=vec3_from(md.get("emission", [0.0, 0.0, 0.0])))

def camera_from_scene(scene: Dict[str, Any]) -> Camera:
    c = scene["camera"]
    return Camera(vec3_from(c["origin"]), vec3_from(c["target"]), vec3_from(c["up"]), float(c["fov_degrees"]))

def lights_from_scene(scene: Dict[str, Any]) -> List[Light]:
    return [Light(vec3_from(l["position"]), vec3_from(l["color"]), float(l["intensity"])) for l in scene.get("lights", [])]

def objects_from_scene(scene: Dict[str, Any]) -> List[Dict[str, Any]]:
    return copy.deepcopy(scene.get("objects", []))



def _vec3_tuple(v: Sequence[float]) -> tuple[float, float, float]:
    return (float(v[0]), float(v[1]), float(v[2]))


def _bound_sphere_from_node(compiled: Dict[str, Any]) -> tuple[float, float, float, float] | None:
    kind = compiled.get("kind", "")
    if kind == "sphere":
        cx, cy, cz = compiled["center"]
        return (cx, cy, cz, float(compiled["radius"]))
    if kind == "box":
        cx, cy, cz = compiled["center"]
        hx, hy, hz = compiled["half_size"]
        return (cx, cy, cz, math.sqrt(hx * hx + hy * hy + hz * hz))
    if kind == "plane":
        return None

    children = compiled.get("children", []) or []
    if not children:
        return None

    if kind == "subtract":
        return children[0].get("bound_sphere")

    child_bounds = [child.get("bound_sphere") for child in children]
    child_bounds = [b for b in child_bounds if b is not None]
    if not child_bounds:
        return None
    if len(child_bounds) == 1:
        bx, by, bz, br = child_bounds[0]
        if kind == "smooth_union":
            br += max(0.0, float(compiled.get("k", 0.0)))
        return (bx, by, bz, br)

    sum_x = sum(b[0] for b in child_bounds)
    sum_y = sum(b[1] for b in child_bounds)
    sum_z = sum(b[2] for b in child_bounds)
    inv_n = 1.0 / float(len(child_bounds))
    cx = sum_x * inv_n
    cy = sum_y * inv_n
    cz = sum_z * inv_n
    radius = 0.0
    for bx, by, bz, br in child_bounds:
        dx = bx - cx
        dy = by - cy
        dz = bz - cz
        radius = max(radius, math.sqrt(dx * dx + dy * dy + dz * dz) + br)
    if kind == "smooth_union":
        radius += max(0.0, float(compiled.get("k", 0.0)))
    return (cx, cy, cz, radius)


def _aabb_from_min_max(min_x: float, min_y: float, min_z: float, max_x: float, max_y: float, max_z: float) -> tuple[float, float, float, float, float, float]:
    cx = 0.5 * (min_x + max_x)
    cy = 0.5 * (min_y + max_y)
    cz = 0.5 * (min_z + max_z)
    hx = 0.5 * (max_x - min_x)
    hy = 0.5 * (max_y - min_y)
    hz = 0.5 * (max_z - min_z)
    return (cx, cy, cz, hx, hy, hz)


def _merge_aabbs(aabbs: Sequence[tuple[float, float, float, float, float, float]]) -> tuple[float, float, float, float, float, float] | None:
    valid = [a for a in aabbs if a is not None]
    if not valid:
        return None
    min_x = min(a[0] - a[3] for a in valid)
    min_y = min(a[1] - a[4] for a in valid)
    min_z = min(a[2] - a[5] for a in valid)
    max_x = max(a[0] + a[3] for a in valid)
    max_y = max(a[1] + a[4] for a in valid)
    max_z = max(a[2] + a[5] for a in valid)
    return _aabb_from_min_max(min_x, min_y, min_z, max_x, max_y, max_z)


def _intersect_aabbs(aabbs: Sequence[tuple[float, float, float, float, float, float]]) -> tuple[float, float, float, float, float, float] | None:
    valid = [a for a in aabbs if a is not None]
    if not valid:
        return None
    min_x = max(a[0] - a[3] for a in valid)
    min_y = max(a[1] - a[4] for a in valid)
    min_z = max(a[2] - a[5] for a in valid)
    max_x = min(a[0] + a[3] for a in valid)
    max_y = min(a[1] + a[4] for a in valid)
    max_z = min(a[2] + a[5] for a in valid)
    if min_x > max_x:
        mid = 0.5 * (min_x + max_x)
        min_x = max_x = mid
    if min_y > max_y:
        mid = 0.5 * (min_y + max_y)
        min_y = max_y = mid
    if min_z > max_z:
        mid = 0.5 * (min_z + max_z)
        min_z = max_z = mid
    return _aabb_from_min_max(min_x, min_y, min_z, max_x, max_y, max_z)


def _expand_aabb(aabb: tuple[float, float, float, float, float, float] | None, amount: float) -> tuple[float, float, float, float, float, float] | None:
    if aabb is None:
        return None
    cx, cy, cz, hx, hy, hz = aabb
    extra = max(0.0, float(amount))
    return (cx, cy, cz, hx + extra, hy + extra, hz + extra)


def _bound_aabb_from_node(compiled: Dict[str, Any]) -> tuple[float, float, float, float, float, float] | None:
    kind = compiled.get("kind", "")
    if kind == "sphere":
        cx, cy, cz = compiled["center"]
        r = float(compiled["radius"])
        return (cx, cy, cz, r, r, r)
    if kind == "box":
        cx, cy, cz = compiled["center"]
        hx, hy, hz = compiled["half_size"]
        c = abs(float(compiled.get("rot_cos", 1.0)))
        s = abs(float(compiled.get("rot_sin", 0.0)))
        ex = c * hx + s * hz
        ey = hy
        ez = s * hx + c * hz
        return (cx, cy, cz, ex, ey, ez)
    if kind == "plane":
        return None

    children = compiled.get("children", []) or []
    if not children:
        return None
    if kind == "subtract":
        return children[0].get("bound_aabb")

    child_aabbs = [child.get("bound_aabb") for child in children]
    bounded = [a for a in child_aabbs if a is not None]
    if not bounded:
        return None
    if kind == "union":
        return _merge_aabbs(bounded)
    if kind == "smooth_union":
        return _expand_aabb(_merge_aabbs(bounded), float(compiled.get("k", 0.0)))
    if kind == "intersection":
        return _intersect_aabbs(bounded)
    return _merge_aabbs(bounded)


def _choose_bound_mode(compiled: Dict[str, Any]) -> str:
    kind = compiled.get("kind", "")
    sphere = compiled.get("bound_sphere")
    aabb = compiled.get("bound_aabb")
    if sphere is None and aabb is None:
        return "none"
    if kind == "sphere":
        return "sphere"
    if kind == "plane":
        return "none"
    if sphere is None:
        return "aabb"
    if aabb is None:
        return "sphere"
    _, _, _, r = sphere
    _, _, _, hx, hy, hz = aabb
    sphere_cube_volume = max(r, 1e-9) ** 3
    aabb_volume = max(hx * hy * hz, 0.0)
    tightness_ratio = aabb_volume / sphere_cube_volume
    if tightness_ratio <= 0.40:
        return "aabb"
    return "sphere"


def _raw_material_tuple(material: Material) -> tuple[float, float, float, float, float, float, float, float, float]:
    return (
        float(material.color.x),
        float(material.color.y),
        float(material.color.z),
        float(material.roughness),
        float(material.metallic),
        float(material.reflectivity),
        float(material.emission.x),
        float(material.emission.y),
        float(material.emission.z),
    )


def compile_object_node(node: Dict[str, Any]) -> Dict[str, Any]:
    kind = str(node.get("kind") or "")
    obj_id = str(node.get("id") or kind)
    params = node.get("params", {}) or {}
    compiled: Dict[str, Any] = {"kind": kind, "id": obj_id}
    if kind in {"sphere", "plane", "box"}:
        compiled["material"] = material_from_dict(node.get("material", {}))
        compiled["material_raw"] = _raw_material_tuple(compiled["material"])
    if kind == "sphere":
        compiled["center"] = _vec3_tuple(params.get("center", (0.0, 0.0, 0.0)))
        compiled["radius"] = float(params.get("radius", 0.0))
        compiled["bound_sphere"] = _bound_sphere_from_node(compiled)
        compiled["bound_aabb"] = _bound_aabb_from_node(compiled)
        compiled["bound_mode"] = "sphere"
        return compiled
    if kind == "plane":
        normal = vec3_from(params.get("normal", (0.0, 1.0, 0.0))).normalized()
        compiled["normal"] = (normal.x, normal.y, normal.z)
        compiled["offset"] = float(params.get("offset", 0.0))
        compiled["bound_sphere"] = None
        compiled["bound_aabb"] = None
        compiled["bound_mode"] = "none"
        return compiled
    if kind == "box":
        compiled["center"] = _vec3_tuple(params.get("center", (0.0, 0.0, 0.0)))
        compiled["half_size"] = _vec3_tuple(params.get("half_size", (0.5, 0.5, 0.5)))
        rotation_y = float(params.get("rotation_y", 0.0))
        compiled["rotation_y"] = rotation_y
        compiled["rot_cos"] = math.cos(rotation_y)
        compiled["rot_sin"] = math.sin(rotation_y)
        compiled["bound_sphere"] = _bound_sphere_from_node(compiled)
        compiled["bound_aabb"] = _bound_aabb_from_node(compiled)
        compiled["bound_mode"] = _choose_bound_mode(compiled)
        return compiled
    compiled["children"] = [compile_object_node(child) for child in node.get("children", [])]
    if kind == "smooth_union":
        compiled["k"] = float(params.get("k", 0.25))
    if "material" in node:
        compiled["material"] = material_from_dict(node.get("material", {}))
        compiled["material_raw"] = _raw_material_tuple(compiled["material"])
    compiled["bound_sphere"] = _bound_sphere_from_node(compiled)
    compiled["bound_aabb"] = _bound_aabb_from_node(compiled)
    compiled["bound_mode"] = _choose_bound_mode(compiled)
    return compiled


def compile_scene(scene: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "camera": camera_from_scene(scene),
        "lights": lights_from_scene(scene),
        "objects": [compile_object_node(obj) for obj in scene.get("objects", [])],
    }

def replace_numeric_with_zero(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: replace_numeric_with_zero(v) for k, v in node.items()}
    if isinstance(node, list):
        return [replace_numeric_with_zero(v) for v in node]
    if isinstance(node, (int, float)):
        return 0.0
    return node

def flatten_numeric_paths(node: Any, prefix: str = "") -> Dict[str, float]:
    out: Dict[str, float] = {}
    if isinstance(node, dict):
        for k, v in node.items():
            key = f"{prefix}.{k}" if prefix else k
            out.update(flatten_numeric_paths(v, key))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            key = f"{prefix}.{i}" if prefix else str(i)
            out.update(flatten_numeric_paths(v, key))
    elif isinstance(node, (int, float)):
        out[prefix] = float(node)
    return out

def set_by_path(node: Any, path: str, value: float) -> None:
    parts = path.split(".")
    cur = node
    for p in parts[:-1]:
        cur = cur[int(p)] if isinstance(cur, list) else cur[p]
    leaf = parts[-1]
    if isinstance(cur, list):
        cur[int(leaf)] = value
    else:
        cur[leaf] = value


def home_scene_choices() -> List[tuple[str, str]]:
    return [
        ("Off", "off"),
        ("Demo Blob", "demo"),
        ("City Sunset", "city"),
        ("Tropical Island", "island"),
        ("Beach Ball", "beach_ball"),
        ("Dog", "dog"),
    ]


def _mat(color, roughness=0.4, metallic=0.0, reflectivity=0.0, emission=None):
    return {
        "color": list(color),
        "roughness": float(roughness),
        "metallic": float(metallic),
        "reflectivity": float(reflectivity),
        "emission": list(emission or [0.0, 0.0, 0.0]),
    }


def city_scene() -> Dict[str, Any]:
    return {
        "camera": {"origin": [0.0, 0.8, -8.0], "target": [0.0, 0.4, 6.0], "up": [0.0, 1.0, 0.0], "fov_degrees": 42.0},
        "lights": [
            {"id": "sun", "position": [-6.0, 5.5, -4.0], "color": [1.0, 0.76, 0.55], "intensity": 2.2},
            {"id": "fill", "position": [5.0, 4.0, -2.0], "color": [0.45, 0.58, 0.95], "intensity": 0.5},
        ],
        "objects": [
            {"id": "ground", "kind": "plane", "params": {"normal": [0.0, 1.0, 0.0], "offset": 1.0}, "material": _mat([0.10, 0.11, 0.14], 0.98, 0.0, 0.03)},
            make_box_node("tower_1", [-3.2, 0.0, 7.5], [0.55, 1.0, 0.55], 0.0, _mat([0.16, 0.20, 0.30], 0.35, 0.05, 0.10)),
            make_box_node("tower_2", [-1.8, 0.2, 7.1], [0.50, 1.2, 0.50], 0.0, _mat([0.18, 0.22, 0.34], 0.35, 0.05, 0.10)),
            make_box_node("tower_3", [-0.5, -0.1, 7.7], [0.60, 0.9, 0.60], 0.0, _mat([0.14, 0.18, 0.28], 0.35, 0.05, 0.10)),
            make_box_node("tower_4", [1.1, 0.35, 7.4], [0.60, 1.35, 0.60], 0.0, _mat([0.20, 0.24, 0.36], 0.35, 0.05, 0.10)),
            make_box_node("tower_5", [2.6, 0.0, 7.9], [0.65, 1.0, 0.65], 0.0, _mat([0.18, 0.20, 0.30], 0.35, 0.05, 0.10)),
            make_box_node("tower_6", [4.1, -0.15, 8.2], [0.70, 0.85, 0.70], 0.0, _mat([0.15, 0.18, 0.26], 0.35, 0.05, 0.10)),
            make_box_node("road", [0.0, -0.92, 4.0], [1.6, 0.03, 7.5], 0.0, _mat([0.08, 0.08, 0.09], 0.95, 0.0, 0.01)),
            make_sphere_node("sun", [-5.0, 3.0, 8.5], 0.9, _mat([1.0, 0.75, 0.35], 1.0, 0.0, 0.0, [0.85, 0.45, 0.12])),
        ],
    }


def tropical_island_scene() -> Dict[str, Any]:
    return {
        "camera": {"origin": [0.0, 0.9, -7.8], "target": [0.0, 0.0, 6.0], "up": [0.0, 1.0, 0.0], "fov_degrees": 44.0},
        "lights": [
            {"id": "sun", "position": [5.0, 6.5, -4.0], "color": [1.0, 0.98, 0.94], "intensity": 2.4},
            {"id": "sky", "position": [-6.0, 4.0, -1.0], "color": [0.35, 0.70, 1.0], "intensity": 0.4},
        ],
        "objects": [
            {"id": "water", "kind": "plane", "params": {"normal": [0.0, 1.0, 0.0], "offset": 1.0}, "material": _mat([0.14, 0.64, 0.76], 0.08, 0.0, 0.46)},
            {"id": "island", "kind": "smooth_union", "params": {"k": 0.55}, "children": [
                make_sphere_node("base1", [-0.8, -0.35, 6.0], 1.45, _mat([0.80, 0.74, 0.48], 1.0, 0.0, 0.02)),
                make_sphere_node("base2", [0.9, -0.28, 6.3], 1.30, _mat([0.82, 0.76, 0.50], 1.0, 0.0, 0.02)),
                make_sphere_node("hill", [0.2, 0.7, 6.2], 1.2, _mat([0.18, 0.54, 0.24], 0.95, 0.0, 0.02)),
            ]},
            make_box_node("palm_trunk", [-0.7, 0.15, 5.1], [0.10, 0.85, 0.10], 0.18, _mat([0.42, 0.26, 0.12], 0.9, 0.0, 0.02)),
            make_box_node("palm_leaf_a", [-0.35, 1.05, 5.1], [0.55, 0.05, 0.14], 0.15, _mat([0.16, 0.52, 0.18], 0.95, 0.0, 0.02)),
            make_box_node("palm_leaf_b", [-1.0, 1.02, 5.3], [0.52, 0.05, 0.13], 1.0, _mat([0.18, 0.54, 0.18], 0.95, 0.0, 0.02)),
            make_box_node("palm_leaf_c", [-0.7, 1.00, 4.6], [0.52, 0.05, 0.13], -0.85, _mat([0.18, 0.58, 0.18], 0.95, 0.0, 0.02)),
        ],
    }


def beach_ball_scene() -> Dict[str, Any]:
    return {
        "camera": {"origin": [0.0, 0.3, -4.6], "target": [0.0, -0.15, 4.4], "up": [0.0, 1.0, 0.0], "fov_degrees": 46.0},
        "lights": [
            {"id": "sun", "position": [4.5, 6.0, -3.5], "color": [1.0, 0.97, 0.92], "intensity": 2.1},
            {"id": "skyfill", "position": [-5.0, 4.0, -2.0], "color": [0.42, 0.62, 1.0], "intensity": 0.45},
        ],
        "objects": [
            {"id": "sand", "kind": "plane", "params": {"normal": [0.0, 1.0, 0.0], "offset": 0.9}, "material": _mat([0.92, 0.82, 0.58], 1.0, 0.0, 0.02)},
            make_sphere_node("ball_white", [0.0, -0.1, 4.0], 0.95, _mat([0.95, 0.95, 0.95], 0.18, 0.0, 0.35)),
            make_box_node("ball_red", [-0.75, -0.1, 4.0], [0.45, 1.1, 1.1], 0.05, _mat([0.95, 0.20, 0.18], 0.22, 0.0, 0.18)),
            make_box_node("ball_blue", [0.78, -0.1, 4.0], [0.42, 1.1, 1.1], -0.02, _mat([0.16, 0.42, 0.92], 0.22, 0.0, 0.18)),
            make_box_node("ball_yellow", [0.0, 0.65, 4.0], [1.2, 0.26, 1.2], 0.0, _mat([0.98, 0.82, 0.22], 0.22, 0.0, 0.18)),
            make_box_node("water", [0.0, -0.62, 9.0], [8.0, 0.02, 6.0], 0.0, _mat([0.18, 0.64, 0.82], 0.10, 0.0, 0.42)),
        ],
    }


def stylized_dog_scene() -> Dict[str, Any]:
    fur = _mat([0.82, 0.64, 0.34], 0.82, 0.0, 0.04)
    fur_light = _mat([0.86, 0.70, 0.40], 0.82, 0.0, 0.04)
    return {
        "camera": {"origin": [0.0, 0.6, -6.0], "target": [0.0, -0.1, 5.2], "up": [0.0, 1.0, 0.0], "fov_degrees": 42.0},
        "lights": [
            {"id": "sun", "position": [4.5, 6.0, -3.2], "color": [1.0, 0.95, 0.90], "intensity": 2.0},
            {"id": "fill", "position": [-5.0, 3.5, -1.8], "color": [0.42, 0.62, 1.0], "intensity": 0.38},
        ],
        "objects": [
            {"id": "ground", "kind": "plane", "params": {"normal": [0.0, 1.0, 0.0], "offset": 1.0}, "material": _mat([0.28, 0.60, 0.24], 0.98, 0.0, 0.02)},
            {"id": "dog_body", "kind": "smooth_union", "params": {"k": 0.42}, "children": [
                make_sphere_node("torso", [0.0, -0.05, 5.4], 0.90, fur),
                make_sphere_node("chest", [0.0, 0.08, 4.9], 0.60, fur_light),
                make_sphere_node("head", [0.0, 0.52, 4.3], 0.55, fur_light),
            ]},
            make_box_node("ear_l", [-0.42, 0.56, 4.26], [0.12, 0.28, 0.08], 0.25, _mat([0.70, 0.48, 0.22], 0.9, 0.0, 0.02)),
            make_box_node("ear_r", [0.42, 0.56, 4.26], [0.12, 0.28, 0.08], -0.25, _mat([0.70, 0.48, 0.22], 0.9, 0.0, 0.02)),
            make_box_node("leg_fl", [-0.34, -0.72, 5.0], [0.10, 0.35, 0.10], 0.0, _mat([0.82, 0.64, 0.34], 0.88, 0.0, 0.02)),
            make_box_node("leg_fr", [0.34, -0.72, 5.0], [0.10, 0.35, 0.10], 0.0, _mat([0.82, 0.64, 0.34], 0.88, 0.0, 0.02)),
            make_box_node("leg_bl", [-0.34, -0.72, 5.85], [0.10, 0.35, 0.10], 0.0, _mat([0.82, 0.64, 0.34], 0.88, 0.0, 0.02)),
            make_box_node("leg_br", [0.34, -0.72, 5.85], [0.10, 0.35, 0.10], 0.0, _mat([0.82, 0.64, 0.34], 0.88, 0.0, 0.02)),
            make_sphere_node("nose", [0.0, 0.40, 3.75], 0.10, _mat([0.08, 0.08, 0.10], 0.2, 0.1, 0.18)),
            make_sphere_node("ball", [1.25, -0.62, 4.35], 0.32, _mat([0.94, 0.18, 0.16], 0.22, 0.0, 0.20)),
        ],
    }


def home_scene_by_name(name: str) -> Dict[str, Any]:
    key = str(name or '').strip().lower()
    if key in {'', 'demo', 'sample'}:
        return sample_scene()
    if key == 'city':
        return city_scene()
    if key == 'island':
        return tropical_island_scene()
    if key in {'beach_ball', 'beachball'}:
        return beach_ball_scene()
    if key == 'dog':
        return stylized_dog_scene()
    raise ValueError(f'Unsupported home scene preset: {name}')
