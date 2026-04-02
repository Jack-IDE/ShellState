"""Low-level math types and helpers for the ShellState graphics subsystem."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

EPSILON = 1e-4
NORMAL_EPS = 7e-4
MAX_STEPS = 180
MAX_DISTANCE = 120.0
SHADOW_STEPS = 56
AO_STEPS = 5
REFLECTION_BOUNCES = 1
SKY_TOP = (0.62, 0.76, 0.96)
SKY_HORIZON = (0.93, 0.95, 0.99)

@dataclass(frozen=True)
class Vec3:
    x: float
    y: float
    z: float
    def __add__(self, o: "Vec3") -> "Vec3":
        return Vec3(self.x + o.x, self.y + o.y, self.z + o.z)
    def __sub__(self, o: "Vec3") -> "Vec3":
        return Vec3(self.x - o.x, self.y - o.y, self.z - o.z)
    def __mul__(self, s: float) -> "Vec3":
        return Vec3(self.x * s, self.y * s, self.z * s)
    __rmul__ = __mul__
    def __truediv__(self, s: float) -> "Vec3":
        return Vec3(self.x / s, self.y / s, self.z / s)
    def dot(self, o: "Vec3") -> float:
        return self.x * o.x + self.y * o.y + self.z * o.z
    def cross(self, o: "Vec3") -> "Vec3":
        return Vec3(self.y * o.z - self.z * o.y, self.z * o.x - self.x * o.z, self.x * o.y - self.y * o.x)
    def length(self) -> float:
        return math.sqrt(self.dot(self))
    def normalized(self) -> "Vec3":
        l = self.length()
        if l <= 1e-12:
            return Vec3(0.0, 0.0, 0.0)
        return self / l
    def hadamard(self, o: "Vec3") -> "Vec3":
        return Vec3(self.x * o.x, self.y * o.y, self.z * o.z)
    def clamp01(self) -> "Vec3":
        return Vec3(clamp(self.x, 0.0, 1.0), clamp(self.y, 0.0, 1.0), clamp(self.z, 0.0, 1.0))

@dataclass(frozen=True)
class Ray:
    origin: Vec3
    direction: Vec3

@dataclass(frozen=True)
class Material:
    color: Vec3
    roughness: float = 0.4
    metallic: float = 0.0
    reflectivity: float = 0.0
    emission: Vec3 = Vec3(0.0, 0.0, 0.0)

@dataclass(frozen=True)
class Camera:
    origin: Vec3
    target: Vec3
    up: Vec3
    fov_degrees: float

@dataclass(frozen=True)
class Light:
    position: Vec3
    color: Vec3
    intensity: float

@dataclass(frozen=True)
class Hit:
    hit: bool
    distance: float
    position: Vec3
    normal: Vec3
    material: Material | None
    object_id: str

@dataclass(frozen=True)
class EvalResult:
    distance: float
    material: Material
    object_id: str

def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v

def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t

def smooth_min(a: float, b: float, k: float) -> float:
    if k <= 0.0:
        return a if a < b else b
    h = clamp(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return lerp(b, a, h) - k * h * (1.0 - h)

def reflect(i: Vec3, n: Vec3) -> Vec3:
    return i - n * (2.0 * i.dot(n))

def rotate_y(p: Vec3, angle: float) -> Vec3:
    c = math.cos(angle)
    s = math.sin(angle)
    return Vec3(c * p.x + s * p.z, p.y, -s * p.x + c * p.z)

def vec3_from(v: Sequence[float]) -> Vec3:
    return Vec3(float(v[0]), float(v[1]), float(v[2]))

def sky_color(direction: Vec3) -> Vec3:
    t = clamp(0.5 * (direction.y + 1.0), 0.0, 1.0)
    return Vec3(*SKY_HORIZON) * (1.0 - t) + Vec3(*SKY_TOP) * t

def schlick_fresnel(cos_theta: float, f0: float) -> float:
    m = clamp(1.0 - cos_theta, 0.0, 1.0)
    return f0 + (1.0 - f0) * (m ** 5)

def solve_linear_system(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    n = len(rhs)
    a = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]
    for i in range(n):
        pivot = i
        for r in range(i + 1, n):
            if abs(a[r][i]) > abs(a[pivot][i]):
                pivot = r
        if abs(a[pivot][i]) < 1e-12:
            continue
        if pivot != i:
            a[i], a[pivot] = a[pivot], a[i]
        div = a[i][i]
        for c in range(i, n + 1):
            a[i][c] /= div
        for r in range(n):
            if r == i:
                continue
            factor = a[r][i]
            if factor == 0.0:
                continue
            for c in range(i, n + 1):
                a[r][c] -= factor * a[i][c]
    return [a[i][n] for i in range(n)]

def mix_material(a: Material, b: Material, t: float) -> Material:
    t = clamp(t, 0.0, 1.0)
    return Material(
        color=a.color * (1.0 - t) + b.color * t,
        roughness=lerp(a.roughness, b.roughness, t),
        metallic=lerp(a.metallic, b.metallic, t),
        reflectivity=lerp(a.reflectivity, b.reflectivity, t),
        emission=a.emission * (1.0 - t) + b.emission * t,
    )

def hash_noise(x: int, y: int, s: int) -> float:
    n = (x * 1973 + y * 9277 + s * 26699 + 0x68BC21EB) & 0xFFFFFFFF
    n = (n ^ (n >> 13)) * 1274126177 & 0xFFFFFFFF
    n = n ^ (n >> 16)
    return (n & 0xFFFFFF) / float(0x1000000)
