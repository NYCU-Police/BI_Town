"""Process-wide world singleton. Backend is the source of truth."""

from app.simulation.world import World

world = World()


def reset_world() -> World:
    global world
    world = World()
    return world
