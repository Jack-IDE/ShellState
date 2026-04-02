"""Minimal stdlib-only 2D game runtime seed for the graphics subsystem."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

from .image2d import Canvas2D

@dataclass
class GameEntity:
    entity_id: str
    x: float
    y: float
    vx: float
    vy: float
    radius: float
    color: Tuple[float, float, float]

@dataclass
class GameWorld:
    width: float = 1.0
    height: float = 1.0
    entities: List[GameEntity] = field(default_factory=list)
    tick: int = 0

def sample_world() -> GameWorld:
    return GameWorld(
        entities=[
            GameEntity('player', 0.18, 0.28, 0.34, 0.22, 0.055, (0.95, 0.52, 0.24)),
            GameEntity('drone_a', 0.72, 0.30, -0.22, 0.27, 0.040, (0.30, 0.72, 0.98)),
            GameEntity('drone_b', 0.58, 0.72, 0.18, -0.24, 0.046, (0.72, 0.92, 0.46)),
        ]
    )

def clone_world(world: GameWorld) -> GameWorld:
    return GameWorld(
        width=float(world.width),
        height=float(world.height),
        entities=[GameEntity(e.entity_id, e.x, e.y, e.vx, e.vy, e.radius, tuple(e.color)) for e in world.entities],
        tick=int(world.tick),
    )

def step_world(world: GameWorld, dt: float = 1.0 / 24.0) -> GameWorld:
    out = clone_world(world)
    out.tick += 1
    for entity in out.entities:
        entity.x += entity.vx * dt
        entity.y += entity.vy * dt
        if entity.x - entity.radius < 0.0:
            entity.x = entity.radius
            entity.vx = abs(entity.vx)
        elif entity.x + entity.radius > out.width:
            entity.x = out.width - entity.radius
            entity.vx = -abs(entity.vx)
        if entity.y - entity.radius < 0.0:
            entity.y = entity.radius
            entity.vy = abs(entity.vy)
        elif entity.y + entity.radius > out.height:
            entity.y = out.height - entity.radius
            entity.vy = -abs(entity.vy)
    return out

def world_snapshot(world: GameWorld) -> Dict[str, object]:
    return {
        'tick': int(world.tick),
        'width': float(world.width),
        'height': float(world.height),
        'entities': [
            {
                'id': e.entity_id,
                'x': round(e.x, 6),
                'y': round(e.y, 6),
                'vx': round(e.vx, 6),
                'vy': round(e.vy, 6),
                'radius': round(e.radius, 6),
                'color': list(e.color),
            }
            for e in world.entities
        ],
    }

def render_world_frame(world: GameWorld, width: int = 256, height: int = 144):
    canvas = Canvas2D(width, height)
    canvas.gradient_vertical((0.05, 0.07, 0.10), (0.10, 0.12, 0.16))
    canvas.rect(0, int(height * 0.84), width, max(1, height - int(height * 0.84)), (0.14, 0.16, 0.22), fill=True)
    canvas.rect(0, 0, width, height, (0.34, 0.42, 0.56), fill=False)
    for entity in world.entities:
        px = entity.x / max(1e-9, world.width)
        py = entity.y / max(1e-9, world.height)
        cx = int(round(px * (width - 1)))
        cy = int(round(py * (height - 1)))
        radius_px = max(3, int(round(entity.radius * min(width, height))))
        canvas.circle(cx, cy, radius_px, entity.color, fill=True)
        canvas.circle(cx, cy, radius_px + 2, (1.0, 1.0, 1.0), fill=False)
    return canvas.rows()

def simulate_world_frames(num_frames: int, width: int = 256, height: int = 144, dt: float = 1.0 / 24.0):
    frames = []
    states = []
    world = sample_world()
    for _ in range(max(1, int(num_frames))):
        frames.append(render_world_frame(world, width=width, height=height))
        states.append(world_snapshot(world))
        world = step_world(world, dt=dt)
    return frames, states
