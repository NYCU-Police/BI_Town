from typing import Literal

from pydantic import BaseModel

AgentState = Literal["idle", "walking"]
WorldEventType = Literal["left", "entered"]


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class Position(BaseModel):
    x: float
    y: float


class WorldState(BaseModel):
    day: int
    time: str
    agent_count: int


class Agent(BaseModel):
    id: str
    name: str
    position: Position
    location: str
    target_location: str
    state: AgentState


class WorldEvent(BaseModel):
    timestamp: str
    agent_id: str
    event: WorldEventType
    location: str


class WorldSnapshot(BaseModel):
    day: int
    time: str
    agents: list[Agent]
    events: list[WorldEvent]


class WorldSnapshotMessage(BaseModel):
    type: Literal["world_snapshot"] = "world_snapshot"
    data: WorldSnapshot


class AgentUpdateData(BaseModel):
    day: int
    time: str
    agents: list[Agent]


class AgentUpdateMessage(BaseModel):
    type: Literal["agent_update"] = "agent_update"
    data: AgentUpdateData


class WorldEventMessage(BaseModel):
    type: Literal["world_event"] = "world_event"
    data: WorldEvent
