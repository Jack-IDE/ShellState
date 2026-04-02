"""Ray-marched field renderer."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Sequence, Tuple

from .math3d import (
    AO_STEPS,
    EPSILON,
    MAX_DISTANCE,
    MAX_STEPS,
    NORMAL_EPS,
    REFLECTION_BOUNCES,
    SHADOW_STEPS,
    SKY_HORIZON,
    SKY_TOP,
    Camera,
    EvalResult,
    Hit,
    Material,
    Ray,
    Vec3,
    clamp,
    hash_noise,
    lerp,
    smooth_min,
)
from .scene import compile_scene

RawMaterial = tuple[float, float, float, float, float, float, float, float, float]
CompiledNode = Dict[str, Any]
ProgressCallback = Callable[[int, int, int, int, List[List[Tuple[int, int, int]]]], None]

_DEFAULT_MATERIAL = Material(Vec3(0.8, 0.8, 0.8))
_DEFAULT_MATERIAL_RAW: RawMaterial = (0.8, 0.8, 0.8, 0.4, 0.0, 0.0, 0.0, 0.0, 0.0)
_EMPTY_RESULT = EvalResult(MAX_DISTANCE, _DEFAULT_MATERIAL, "")


@dataclass(frozen=True)
class PreparedCamera:
    ox: float
    oy: float
    oz: float
    fx: float
    fy: float
    fz: float
    rx: float
    ry: float
    rz: float
    ux: float
    uy: float
    uz: float
    aspect: float
    scale: float


@dataclass(frozen=True)
class RawHit:
    hit: bool
    distance: float
    px: float
    py: float
    pz: float
    nx: float
    ny: float
    nz: float
    material_raw: RawMaterial | None
    object_id: str


def _length3(x: float, y: float, z: float) -> float:
    return math.sqrt(x * x + y * y + z * z)


def _dot3(ax: float, ay: float, az: float, bx: float, by: float, bz: float) -> float:
    return ax * bx + ay * by + az * bz


def _normalize3(x: float, y: float, z: float) -> tuple[float, float, float]:
    l = math.sqrt(x * x + y * y + z * z)
    if l <= 1e-12:
        return (0.0, 0.0, 0.0)
    inv = 1.0 / l
    return (x * inv, y * inv, z * inv)


def _raw_material_to_object(raw: RawMaterial) -> Material:
    return Material(
        color=Vec3(raw[0], raw[1], raw[2]),
        roughness=raw[3],
        metallic=raw[4],
        reflectivity=raw[5],
        emission=Vec3(raw[6], raw[7], raw[8]),
    )


def _mix_material_raw(a: RawMaterial, b: RawMaterial, t: float) -> RawMaterial:
    t = clamp(t, 0.0, 1.0)
    omt = 1.0 - t
    return (
        a[0] * omt + b[0] * t,
        a[1] * omt + b[1] * t,
        a[2] * omt + b[2] * t,
        lerp(a[3], b[3], t),
        lerp(a[4], b[4], t),
        lerp(a[5], b[5], t),
        a[6] * omt + b[6] * t,
        a[7] * omt + b[7] * t,
        a[8] * omt + b[8] * t,
    )


def _reflect3(ix: float, iy: float, iz: float, nx: float, ny: float, nz: float) -> tuple[float, float, float]:
    ndot = 2.0 * _dot3(ix, iy, iz, nx, ny, nz)
    return (ix - nx * ndot, iy - ny * ndot, iz - nz * ndot)


def _schlick_fresnel(cos_theta: float, f0: float) -> float:
    m = clamp(1.0 - cos_theta, 0.0, 1.0)
    return f0 + (1.0 - f0) * (m ** 5)


def _sky_color_raw(dy: float) -> tuple[float, float, float]:
    t = clamp(0.5 * (dy + 1.0), 0.0, 1.0)
    omt = 1.0 - t
    return (
        SKY_HORIZON[0] * omt + SKY_TOP[0] * t,
        SKY_HORIZON[1] * omt + SKY_TOP[1] * t,
        SKY_HORIZON[2] * omt + SKY_TOP[2] * t,
    )


def _compile_lights_raw(lights: Sequence[Any]) -> list[tuple[float, float, float, float, float, float, float]]:
    out = []
    for light in lights:
        out.append(
            (
                float(light.position.x),
                float(light.position.y),
                float(light.position.z),
                float(light.color.x),
                float(light.color.y),
                float(light.color.z),
                float(light.intensity),
            )
        )
    return out


def prepare_camera(camera: Camera, width: int, height: int) -> PreparedCamera:
    fx, fy, fz = _normalize3(
        camera.target.x - camera.origin.x,
        camera.target.y - camera.origin.y,
        camera.target.z - camera.origin.z,
    )
    rx, ry, rz = _normalize3(
        fy * camera.up.z - fz * camera.up.y,
        fz * camera.up.x - fx * camera.up.z,
        fx * camera.up.y - fy * camera.up.x,
    )
    ux, uy, uz = _normalize3(
        ry * fz - rz * fy,
        rz * fx - rx * fz,
        rx * fy - ry * fx,
    )
    return PreparedCamera(
        ox=float(camera.origin.x),
        oy=float(camera.origin.y),
        oz=float(camera.origin.z),
        fx=fx,
        fy=fy,
        fz=fz,
        rx=rx,
        ry=ry,
        rz=rz,
        ux=ux,
        uy=uy,
        uz=uz,
        aspect=width / max(1.0, float(height)),
        scale=math.tan(math.radians(camera.fov_degrees) * 0.5),
    )


def build_camera_ray_prepared(u: float, v: float, prepared: PreparedCamera) -> Ray:
    px = (2.0 * u - 1.0) * prepared.aspect * prepared.scale
    py = (1.0 - 2.0 * v) * prepared.scale
    dx = prepared.fx + prepared.rx * px + prepared.ux * py
    dy = prepared.fy + prepared.ry * px + prepared.uy * py
    dz = prepared.fz + prepared.rz * px + prepared.uz * py
    ndx, ndy, ndz = _normalize3(dx, dy, dz)
    return Ray(Vec3(prepared.ox, prepared.oy, prepared.oz), Vec3(ndx, ndy, ndz))


def _build_camera_ray_prepared_raw(u: float, v: float, prepared: PreparedCamera) -> tuple[float, float, float]:
    px = (2.0 * u - 1.0) * prepared.aspect * prepared.scale
    py = (1.0 - 2.0 * v) * prepared.scale
    dx = prepared.fx + prepared.rx * px + prepared.ux * py
    dy = prepared.fy + prepared.ry * px + prepared.uy * py
    dz = prepared.fz + prepared.rz * px + prepared.uz * py
    return _normalize3(dx, dy, dz)


def build_camera_ray_uv(u: float, v: float, width: int, height: int, camera: Camera) -> Ray:
    return build_camera_ray_prepared(u, v, prepare_camera(camera, width, height))


def _bound_sphere_lower_distance(px: float, py: float, pz: float, obj: CompiledNode) -> float:
    bound = obj.get("bound_sphere")
    if bound is None:
        return -MAX_DISTANCE
    cx, cy, cz, radius = bound
    return _length3(px - cx, py - cy, pz - cz) - radius


def _bound_aabb_lower_distance(px: float, py: float, pz: float, obj: CompiledNode) -> float:
    bound = obj.get("bound_aabb")
    if bound is None:
        return -MAX_DISTANCE
    cx, cy, cz, hx, hy, hz = bound
    dx = abs(px - cx) - hx
    dy = abs(py - cy) - hy
    dz = abs(pz - cz) - hz
    mx = max(dx, 0.0)
    my = max(dy, 0.0)
    mz = max(dz, 0.0)
    outside = math.sqrt(mx * mx + my * my + mz * mz)
    inside = min(max(dx, max(dy, dz)), 0.0)
    return outside + inside


def _bound_lower_distance(px: float, py: float, pz: float, obj: CompiledNode) -> float:
    mode = obj.get("bound_mode", "sphere")
    if mode == "aabb":
        return _bound_aabb_lower_distance(px, py, pz, obj)
    if mode == "sphere":
        return _bound_sphere_lower_distance(px, py, pz, obj)
    return -MAX_DISTANCE


def _eval_node_sdf_raw(px: float, py: float, pz: float, obj: CompiledNode) -> tuple[float, RawMaterial, str]:
    return _eval_node_sdf_raw_cutoff(px, py, pz, obj, MAX_DISTANCE)


def _eval_node_sdf_raw_cutoff(px: float, py: float, pz: float, obj: CompiledNode, cutoff: float) -> tuple[float, RawMaterial, str]:
    bound_distance = _bound_lower_distance(px, py, pz, obj)
    if bound_distance >= cutoff:
        return bound_distance, obj.get("material_raw", _DEFAULT_MATERIAL_RAW), obj.get("id", obj.get("kind", ""))

    kind = obj["kind"]
    obj_id = obj.get("id", kind)
    if kind == "sphere":
        cx, cy, cz = obj["center"]
        d = _length3(px - cx, py - cy, pz - cz) - obj["radius"]
        return d, obj["material_raw"], obj_id
    if kind == "plane":
        nx, ny, nz = obj["normal"]
        d = px * nx + py * ny + pz * nz + obj["offset"]
        return d, obj["material_raw"], obj_id
    if kind == "box":
        cx, cy, cz = obj["center"]
        hx, hy, hz = obj["half_size"]
        dx0 = px - cx
        dy0 = py - cy
        dz0 = pz - cz
        c = obj["rot_cos"]
        s = obj["rot_sin"]
        qx = c * dx0 - s * dz0
        qy = dy0
        qz = s * dx0 + c * dz0
        dx = abs(qx) - hx
        dy = abs(qy) - hy
        dz = abs(qz) - hz
        mx = max(dx, 0.0)
        my = max(dy, 0.0)
        mz = max(dz, 0.0)
        outside = math.sqrt(mx * mx + my * my + mz * mz)
        inside = min(max(dx, max(dy, dz)), 0.0)
        return outside + inside, obj["material_raw"], obj_id

    children = obj.get("children", [])
    if not children:
        return MAX_DISTANCE, obj.get("material_raw", _DEFAULT_MATERIAL_RAW), obj_id

    first_distance, first_material, first_object_id = _eval_node_sdf_raw_cutoff(px, py, pz, children[0], cutoff)

    if kind == "union":
        best_distance = first_distance
        best_material = first_material
        best_object_id = first_object_id
        child_cutoff = min(cutoff, best_distance)
        for child in children[1:]:
            child_bound_distance = _bound_lower_distance(px, py, pz, child)
            if child_bound_distance >= child_cutoff:
                continue
            child_distance, child_material, child_object_id = _eval_node_sdf_raw_cutoff(px, py, pz, child, child_cutoff)
            if child_distance < best_distance:
                best_distance = child_distance
                best_material = child_material
                best_object_id = child_object_id
                child_cutoff = min(cutoff, best_distance)
        return best_distance, best_material, obj_id or best_object_id

    if kind == "smooth_union":
        k = float(obj.get("k", 0.25))
        result_distance = first_distance
        result_material = first_material
        result_object_id = obj_id
        for child in children[1:]:
            child_bound_distance = _bound_lower_distance(px, py, pz, child)
            if child_bound_distance >= (result_distance + max(0.0, k)):
                continue
            other_distance, other_material, _other_object_id = _eval_node_sdf_raw_cutoff(px, py, pz, child, result_distance + max(0.0, k))
            if k <= 0.0:
                if other_distance < result_distance:
                    result_distance = other_distance
                    result_material = other_material
                continue
            h = clamp(0.5 + 0.5 * (other_distance - result_distance) / k, 0.0, 1.0)
            result_distance = smooth_min(result_distance, other_distance, k)
            result_material = _mix_material_raw(other_material, result_material, h)
        return result_distance, result_material, result_object_id

    if kind == "subtract":
        cut_distance = MAX_DISTANCE
        for child in children[1:]:
            child_bound_distance = _bound_lower_distance(px, py, pz, child)
            if child_bound_distance >= cut_distance:
                continue
            child_distance, _child_material, _child_object_id = _eval_node_sdf_raw_cutoff(px, py, pz, child, cut_distance)
            if child_distance < cut_distance:
                cut_distance = child_distance
        return max(first_distance, -cut_distance), first_material, obj_id

    if kind == "intersection":
        best_distance = first_distance
        best_material = first_material
        for child in children[1:]:
            child_distance, child_material, _child_object_id = _eval_node_sdf_raw_cutoff(px, py, pz, child, MAX_DISTANCE)
            if child_distance > best_distance:
                best_distance = child_distance
                best_material = child_material
        return best_distance, best_material, obj_id

    raise ValueError(f"Unsupported node kind: {kind}")



def scene_sdf_raw(px: float, py: float, pz: float, objects: Sequence[CompiledNode]) -> tuple[float, RawMaterial, str]:
    best_distance = MAX_DISTANCE
    best_material = _DEFAULT_MATERIAL_RAW
    best_object_id = ""
    for obj in objects:
        bound_distance = _bound_lower_distance(px, py, pz, obj)
        if bound_distance >= best_distance:
            continue
        distance, material, object_id = _eval_node_sdf_raw_cutoff(px, py, pz, obj, best_distance)
        if distance < best_distance:
            best_distance = distance
            best_material = material
            best_object_id = object_id
    return best_distance, best_material, best_object_id



def scene_sdf(p: Vec3, objects: Sequence[CompiledNode]) -> EvalResult:
    distance, material_raw, object_id = scene_sdf_raw(p.x, p.y, p.z, objects)
    return EvalResult(distance, _raw_material_to_object(material_raw), object_id)



def estimate_normal(p: Vec3, objects: Sequence[CompiledNode]) -> Vec3:
    nx, ny, nz = estimate_normal_raw(p.x, p.y, p.z, objects)
    return Vec3(nx, ny, nz)



def estimate_normal_raw(px: float, py: float, pz: float, objects: Sequence[CompiledNode]) -> tuple[float, float, float]:
    e = NORMAL_EPS
    nx = scene_sdf_raw(px + e, py, pz, objects)[0] - scene_sdf_raw(px - e, py, pz, objects)[0]
    ny = scene_sdf_raw(px, py + e, pz, objects)[0] - scene_sdf_raw(px, py - e, pz, objects)[0]
    nz = scene_sdf_raw(px, py, pz + e, objects)[0] - scene_sdf_raw(px, py, pz - e, objects)[0]
    return _normalize3(nx, ny, nz)



def ray_march_raw(ox: float, oy: float, oz: float, dx: float, dy: float, dz: float, objects: Sequence[CompiledNode]) -> RawHit:
    t = 0.0
    for _ in range(MAX_STEPS):
        px = ox + dx * t
        py = oy + dy * t
        pz = oz + dz * t
        distance, material_raw, object_id = scene_sdf_raw(px, py, pz, objects)
        if distance < EPSILON:
            nx, ny, nz = estimate_normal_raw(px, py, pz, objects)
            return RawHit(True, t, px, py, pz, nx, ny, nz, material_raw, object_id)
        t += distance
        if t > MAX_DISTANCE:
            break
    far_t = min(t, MAX_DISTANCE)
    return RawHit(False, t, ox + dx * far_t, oy + dy * far_t, oz + dz * far_t, 0.0, 1.0, 0.0, None, "")



def ray_march(ray: Ray, objects: Sequence[CompiledNode]) -> Hit:
    raw = ray_march_raw(ray.origin.x, ray.origin.y, ray.origin.z, ray.direction.x, ray.direction.y, ray.direction.z, objects)
    material = _raw_material_to_object(raw.material_raw) if raw.material_raw is not None else None
    return Hit(raw.hit, raw.distance, Vec3(raw.px, raw.py, raw.pz), Vec3(raw.nx, raw.ny, raw.nz), material, raw.object_id)



def soft_shadow(origin: Vec3, direction: Vec3, max_t: float, objects: Sequence[CompiledNode]) -> float:
    return soft_shadow_raw(origin.x, origin.y, origin.z, direction.x, direction.y, direction.z, max_t, objects)



def soft_shadow_raw(ox: float, oy: float, oz: float, dx: float, dy: float, dz: float, max_t: float, objects: Sequence[CompiledNode]) -> float:
    if SHADOW_STEPS <= 0:
        return 1.0
    res = 1.0
    t = 0.02
    for _ in range(SHADOW_STEPS):
        if t >= max_t:
            break
        h = scene_sdf_raw(ox + dx * t, oy + dy * t, oz + dz * t, objects)[0]
        if h < EPSILON:
            return 0.0
        res = min(res, 16.0 * h / t)
        t += max(0.02, min(0.35, h))
    return clamp(res, 0.0, 1.0)



def ambient_occlusion(p: Vec3, n: Vec3, objects: Sequence[CompiledNode]) -> float:
    return ambient_occlusion_raw(p.x, p.y, p.z, n.x, n.y, n.z, objects)



def ambient_occlusion_raw(px: float, py: float, pz: float, nx: float, ny: float, nz: float, objects: Sequence[CompiledNode]) -> float:
    if AO_STEPS <= 0:
        return 1.0
    occ = 0.0
    scale = 1.0
    for i in range(AO_STEPS):
        h = 0.08 + 0.12 * i
        d = scene_sdf_raw(px + nx * h, py + ny * h, pz + nz * h, objects)[0]
        occ += max(0.0, h - d) * scale
        scale *= 0.65
    return clamp(1.0 - occ * 1.45, 0.0, 1.0)



def shade_raw(
    ox: float,
    oy: float,
    oz: float,
    dx: float,
    dy: float,
    dz: float,
    hit: RawHit,
    objects: Sequence[CompiledNode],
    lights_raw: Sequence[tuple[float, float, float, float, float, float, float]],
    bounce: int = 0,
) -> tuple[float, float, float]:
    if not hit.hit or hit.material_raw is None:
        return _sky_color_raw(dy)

    px = hit.px
    py = hit.py
    pz = hit.pz
    nx = hit.nx
    ny = hit.ny
    nz = hit.nz
    md = hit.material_raw
    base_r, base_g, base_b = md[0], md[1], md[2]
    roughness, metallic, reflectivity = md[3], md[4], md[5]
    emit_r, emit_g, emit_b = md[6], md[7], md[8]

    vx, vy, vz = _normalize3(ox - px, oy - py, oz - pz)
    sky_nr, sky_ng, sky_nb = _sky_color_raw(ny)
    color_r = emit_r + sky_nr * 0.04
    color_g = emit_g + sky_ng * 0.04
    color_b = emit_b + sky_nb * 0.04
    ao = ambient_occlusion_raw(px, py, pz, nx, ny, nz, objects)

    for lx, ly, lz, lr, lg, lb, intensity in lights_raw:
        ldx = lx - px
        ldy = ly - py
        ldz = lz - pz
        ldist = _length3(ldx, ldy, ldz)
        if ldist <= 1e-8:
            continue
        inv_ldist = 1.0 / ldist
        lnx = ldx * inv_ldist
        lny = ldy * inv_ldist
        lnz = ldz * inv_ldist
        n_dot_l = max(0.0, nx * lnx + ny * lny + nz * lnz)
        if n_dot_l <= 0.0:
            continue
        shadow = soft_shadow_raw(px + nx * (EPSILON * 4.0), py + ny * (EPSILON * 4.0), pz + nz * (EPSILON * 4.0), lnx, lny, lnz, ldist, objects)
        atten = intensity / (1.0 + 0.12 * ldist + 0.04 * ldist * ldist)
        diffuse_scale = n_dot_l * atten * shadow

        hx, hy, hz = _normalize3(lnx + vx, lny + vy, lnz + vz)
        n_dot_h = max(0.0, nx * hx + ny * hy + nz * hz)
        shininess = lerp(8.0, 96.0, 1.0 - clamp(roughness, 0.0, 1.0))
        spec = (n_dot_h ** shininess) * atten * shadow
        f0 = lerp(0.04, 0.85, clamp(metallic, 0.0, 1.0))
        fres = _schlick_fresnel(max(0.0, hx * vx + hy * vy + hz * vz), f0)
        spec_scale = spec * fres

        color_r += base_r * diffuse_scale * lr + spec_scale * lr
        color_g += base_g * diffuse_scale * lg + spec_scale * lg
        color_b += base_b * diffuse_scale * lb + spec_scale * lb

    color_r *= ao
    color_g *= ao
    color_b *= ao

    refl = clamp(reflectivity, 0.0, 1.0)
    if refl > 0.0 and bounce < REFLECTION_BOUNCES:
        rdx, rdy, rdz = _reflect3(dx, dy, dz, nx, ny, nz)
        rdx, rdy, rdz = _normalize3(rdx, rdy, rdz)
        rox = px + nx * (EPSILON * 6.0)
        roy = py + ny * (EPSILON * 6.0)
        roz = pz + nz * (EPSILON * 6.0)
        rhit = ray_march_raw(rox, roy, roz, rdx, rdy, rdz, objects)
        rr, rg, rb = shade_raw(rox, roy, roz, rdx, rdy, rdz, rhit, objects, lights_raw, bounce + 1)
        inv_refl = 1.0 - refl
        color_r = color_r * inv_refl + rr * refl
        color_g = color_g * inv_refl + rg * refl
        color_b = color_b * inv_refl + rb * refl

    return (clamp(color_r, 0.0, 1.0), clamp(color_g, 0.0, 1.0), clamp(color_b, 0.0, 1.0))



def shade(ray: Ray, hit: Hit, objects: Sequence[CompiledNode], lights: Sequence[Any], bounce: int = 0) -> Vec3:
    raw_hit = RawHit(
        hit.hit,
        hit.distance,
        hit.position.x,
        hit.position.y,
        hit.position.z,
        hit.normal.x,
        hit.normal.y,
        hit.normal.z,
        None if hit.material is None else (
            hit.material.color.x,
            hit.material.color.y,
            hit.material.color.z,
            hit.material.roughness,
            hit.material.metallic,
            hit.material.reflectivity,
            hit.material.emission.x,
            hit.material.emission.y,
            hit.material.emission.z,
        ),
        hit.object_id,
    )
    r, g, b = shade_raw(ray.origin.x, ray.origin.y, ray.origin.z, ray.direction.x, ray.direction.y, ray.direction.z, raw_hit, objects, _compile_lights_raw(lights), bounce)
    return Vec3(r, g, b)



def linear_to_srgb(v: float) -> int:
    v = clamp(v, 0.0, 1.0)
    gamma = v ** (1.0 / 2.2)
    return int(gamma * 255.0 + 0.5)



def _progressive_pass_sizes(width: int, height: int) -> list[tuple[int, int]]:
    width = max(1, int(width))
    height = max(1, int(height))
    dims: list[tuple[int, int]] = []
    for divisor in (8, 4, 2, 1):
        pw = max(1, (width + divisor - 1) // divisor)
        ph = max(1, (height + divisor - 1) // divisor)
        if not dims or dims[-1] != (pw, ph):
            dims.append((pw, ph))
    if dims[-1] != (width, height):
        dims.append((width, height))
    return dims



def _render_scene_compiled(compiled: Dict[str, Any], width: int, height: int, spp: int = 1) -> List[List[Tuple[int, int, int]]]:
    camera = compiled["camera"]
    lights_raw = _compile_lights_raw(compiled["lights"])
    objects = compiled["objects"]
    prepared_camera = prepare_camera(camera, width, height)
    framebuffer: List[List[Tuple[int, int, int]]] = []
    spp = max(1, int(spp))
    side = int(math.sqrt(spp))
    stratified = side * side == spp
    inv_width = 1.0 / max(1, int(width))
    inv_height = 1.0 / max(1, int(height))
    ox = prepared_camera.ox
    oy = prepared_camera.oy
    oz = prepared_camera.oz
    for y in range(height):
        row: List[Tuple[int, int, int]] = []
        for x in range(width):
            accum_r = 0.0
            accum_g = 0.0
            accum_b = 0.0
            if stratified:
                sample_index = 0
                for sy in range(side):
                    for sx in range(side):
                        jx = hash_noise(x, y, sample_index) - 0.5
                        jy = hash_noise(x, y, sample_index + 991) - 0.5
                        u = (x + (sx + 0.5 + 0.35 * jx) / side) * inv_width
                        v = (y + (sy + 0.5 + 0.35 * jy) / side) * inv_height
                        dx, dy, dz = _build_camera_ray_prepared_raw(u, v, prepared_camera)
                        hit = ray_march_raw(ox, oy, oz, dx, dy, dz, objects)
                        r, g, b = shade_raw(ox, oy, oz, dx, dy, dz, hit, objects, lights_raw)
                        accum_r += r
                        accum_g += g
                        accum_b += b
                        sample_index += 1
            else:
                for s in range(spp):
                    u = (x + hash_noise(x, y, s)) * inv_width
                    v = (y + hash_noise(x, y, s + 991)) * inv_height
                    dx, dy, dz = _build_camera_ray_prepared_raw(u, v, prepared_camera)
                    hit = ray_march_raw(ox, oy, oz, dx, dy, dz, objects)
                    r, g, b = shade_raw(ox, oy, oz, dx, dy, dz, hit, objects, lights_raw)
                    accum_r += r
                    accum_g += g
                    accum_b += b
            inv_spp = 1.0 / float(spp)
            row.append(
                (
                    linear_to_srgb(accum_r * inv_spp),
                    linear_to_srgb(accum_g * inv_spp),
                    linear_to_srgb(accum_b * inv_spp),
                )
            )
        framebuffer.append(row)
    return framebuffer



def render_scene_progressive(
    scene: Dict[str, Any],
    width: int,
    height: int,
    spp: int = 1,
    *,
    progress_callback: ProgressCallback | None = None,
) -> List[List[Tuple[int, int, int]]]:
    compiled = compile_scene(scene)
    pass_dims = _progressive_pass_sizes(width, height)
    total = len(pass_dims)
    final_framebuffer: List[List[Tuple[int, int, int]]] = []
    for index, (pass_w, pass_h) in enumerate(pass_dims, start=1):
        final_framebuffer = _render_scene_compiled(compiled, pass_w, pass_h, spp=spp)
        if progress_callback is not None:
            progress_callback(index, total, pass_w, pass_h, final_framebuffer)
    return final_framebuffer



def render_scene_with_overrides(
    scene: Dict[str, Any],
    width: int,
    height: int,
    spp: int = 1,
    *,
    max_steps: int | None = None,
    shadow_steps: int | None = None,
    ao_steps: int | None = None,
    reflection_bounces: int | None = None,
) -> List[List[Tuple[int, int, int]]]:
    saved = (MAX_STEPS, SHADOW_STEPS, AO_STEPS, REFLECTION_BOUNCES)
    try:
        if max_steps is not None:
            globals()["MAX_STEPS"] = max(1, int(max_steps))
        if shadow_steps is not None:
            globals()["SHADOW_STEPS"] = max(0, int(shadow_steps))
        if ao_steps is not None:
            globals()["AO_STEPS"] = max(0, int(ao_steps))
        if reflection_bounces is not None:
            globals()["REFLECTION_BOUNCES"] = max(0, int(reflection_bounces))
        return render_scene(scene, width, height, spp=spp)
    finally:
        globals()["MAX_STEPS"], globals()["SHADOW_STEPS"], globals()["AO_STEPS"], globals()["REFLECTION_BOUNCES"] = saved



def render_scene_progressive_with_overrides(
    scene: Dict[str, Any],
    width: int,
    height: int,
    spp: int = 1,
    *,
    max_steps: int | None = None,
    shadow_steps: int | None = None,
    ao_steps: int | None = None,
    reflection_bounces: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> List[List[Tuple[int, int, int]]]:
    saved = (MAX_STEPS, SHADOW_STEPS, AO_STEPS, REFLECTION_BOUNCES)
    try:
        if max_steps is not None:
            globals()["MAX_STEPS"] = max(1, int(max_steps))
        if shadow_steps is not None:
            globals()["SHADOW_STEPS"] = max(0, int(shadow_steps))
        if ao_steps is not None:
            globals()["AO_STEPS"] = max(0, int(ao_steps))
        if reflection_bounces is not None:
            globals()["REFLECTION_BOUNCES"] = max(0, int(reflection_bounces))
        return render_scene_progressive(scene, width, height, spp=spp, progress_callback=progress_callback)
    finally:
        globals()["MAX_STEPS"], globals()["SHADOW_STEPS"], globals()["AO_STEPS"], globals()["REFLECTION_BOUNCES"] = saved



def render_scene(scene: Dict[str, Any], width: int, height: int, spp: int = 1) -> List[List[Tuple[int, int, int]]]:
    compiled = compile_scene(scene)
    return _render_scene_compiled(compiled, width, height, spp=spp)
