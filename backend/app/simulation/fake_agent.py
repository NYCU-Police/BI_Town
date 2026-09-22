"""Rule-based agents. No LLM."""

import logging
import math

from app.config import AGENT_SPEED_PER_TICK, ARRIVAL_DISTANCE_THRESHOLD
from app.models.schemas import Agent, Position, WorldEvent
from app.simulation.poi import POIS

logger = logging.getLogger(__name__)

# (game time, destination POI id)
MINA_SCHEDULE: list[tuple[str, str]] = [
    ("08:00", "cafe"),
    ("09:00", "office"),
    ("12:00", "cafe"),
    ("13:00", "office"),
    ("18:00", "park"),
    ("20:00", "home"),
]

# Offset ~30 minutes; lunch at park instead of cafe.
ALEX_SCHEDULE: list[tuple[str, str]] = [
    ("08:30", "cafe"),
    ("09:30", "office"),
    ("12:00", "park"),
    ("13:30", "office"),
    ("18:30", "park"),
    ("20:30", "home"),
]

SCHEDULES: dict[str, list[tuple[str, str]]] = {
    "mina": MINA_SCHEDULE,
    "alex": ALEX_SCHEDULE,
}


def distance(a: Position, b: Position) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def destination_at(agent_id: str, time: str) -> str | None:
    for scheduled_time, dest in SCHEDULES.get(agent_id, []):
        if scheduled_time == time:
            return dest
    return None


def step_towards(position: Position, target: Position, speed: float) -> Position:
    dist = distance(position, target)
    if dist <= speed:
        return Position(x=target.x, y=target.y)
    ratio = speed / dist
    return Position(
        x=position.x + (target.x - position.x) * ratio,
        y=position.y + (target.y - position.y) * ratio,
    )


def apply_schedule(agent: Agent, time: str) -> WorldEvent | None:
    dest = destination_at(agent.id, time)
    if dest is None:
        return None
    if dest not in POIS:
        logger.error("Schedule points to unknown POI %s for agent %s", dest, agent.id)
        return None
    if agent.state == "idle" and agent.location == dest:
        return None
    if agent.state == "walking" and agent.target_location == dest:
        return None

    event: WorldEvent | None = None
    if agent.state == "idle":
        event = WorldEvent(
            timestamp=time,
            agent_id=agent.id,
            event="left",
            location=agent.location,
        )
    agent.target_location = dest
    agent.state = "walking"
    return event


def move_agent(agent: Agent, time: str) -> WorldEvent | None:
    if agent.state != "walking":
        return None
    if agent.target_location not in POIS:
        logger.error(
            "Agent %s has unknown target_location %s",
            agent.id,
            agent.target_location,
        )
        return None

    target = POIS[agent.target_location]
    target_pos = target.position
    dist = distance(agent.position, target_pos)
    if dist <= ARRIVAL_DISTANCE_THRESHOLD or dist <= AGENT_SPEED_PER_TICK:
        agent.position = target_pos
        agent.location = agent.target_location
        agent.state = "idle"
        return WorldEvent(
            timestamp=time,
            agent_id=agent.id,
            event="entered",
            location=agent.location,
        )

    agent.position = step_towards(agent.position, target_pos, AGENT_SPEED_PER_TICK)
    return None
