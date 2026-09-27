from typing import Literal

from pydantic import BaseModel

AgentState = Literal["idle", "walking", "doing"]
WorldEventType = Literal["left", "entered", "said", "thought", "activity"]


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    git_commit: str
    deployed_at: str
    brain_mode: Literal["rules", "llm"]


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
    activity: str = ""


class WorldEvent(BaseModel):
    timestamp: str
    agent_id: str
    event: WorldEventType
    location: str
    target_agent_id: str | None = None
    content: str | None = None
    duration_minutes: int | None = None


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
