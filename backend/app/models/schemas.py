from typing import Literal

from pydantic import BaseModel, Field

AgentState = Literal["idle", "walking", "doing"]
WorldEventType = Literal[
    "left",
    "entered",
    "said",
    "thought",
    "activity",
    "ate",
    "gave",
    "picked_up",
    "produced",
    "conversing",
    "conversing_ended",
]
IntentAction = Literal[
    "move_to",
    "pick_up",
    "eat",
    "give",
    "use_tool",
    "talk",
    "present_evidence",
    "accuse",
    "next_round",
]
TargetType = Literal["agent", "poi"]


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


class Needs(BaseModel):
    hunger: int
    energy: int
    social: int


class ItemStack(BaseModel):
    id: str
    count: int


class Agent(BaseModel):
    id: str
    name: str
    position: Position
    location: str
    target_location: str
    state: AgentState
    activity: str = ""
    needs: Needs | None = None
    items: list[ItemStack] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    collapsed: bool = False


class WorldEvent(BaseModel):
    timestamp: str
    agent_id: str
    event: WorldEventType
    location: str
    target_agent_id: str | None = None
    content: str | None = None
    duration_minutes: int | None = None
    item: str | None = None


class DialogueTurn(BaseModel):
    speaker_id: str
    reply: str
    role: Literal["player", "resident"] = "resident"
    mood: str | None = None
    reason: str | None = None


class WorldSnapshot(BaseModel):
    day: int
    time: str
    agents: list[Agent]
    events: list[WorldEvent]
    you: str | None = None
    dialogue_history: list[DialogueTurn] = Field(default_factory=list)
    notice: str = ""
    notes: list[str] = Field(default_factory=list)
    note_ids: list[str] = Field(default_factory=list)
    phase: Literal["play", "assembly", "reveal"] = "play"
    motives: list[dict[str, str]] = Field(default_factory=list)
    residents: list[dict[str, str]] = Field(default_factory=list)
    accused: bool = False
    reveal_text: str = ""
    score: int | None = None
    remaining_seconds: int = 0


class WorldSnapshotMessage(BaseModel):
    type: Literal["world_snapshot"] = "world_snapshot"
    data: WorldSnapshot


class AgentUpdateData(BaseModel):
    day: int
    time: str
    agents: list[Agent]
    removed: list[str] | None = None
    notice: str | None = None


class AgentUpdateMessage(BaseModel):
    type: Literal["agent_update"] = "agent_update"
    data: AgentUpdateData


class WorldEventMessage(BaseModel):
    type: Literal["world_event"] = "world_event"
    data: WorldEvent


class TargetRef(BaseModel):
    type: TargetType
    id: str


class Intent(BaseModel):
    action: IntentAction
    target: TargetRef | None = None
    item: str | None = None
    text: str | None = None
    fact_id: str | None = None
    culprit_id: str | None = None
    motive_id: str | None = None


class IntentResultMessage(BaseModel):
    type: Literal["intent_result"] = "intent_result"
    client_seq: int
    ok: bool
    reason: str | None = None


class SessionMessage(BaseModel):
    type: Literal["session"] = "session"
    player_token: str


class GameConfigPoi(BaseModel):
    id: str
    name: str
    x: float
    y: float


class GameConfigItem(BaseModel):
    id: str
    name: str
    food: bool


class GameConfig(BaseModel):
    """一局內不變的規則與內容。

    居民與玩家 Agent 不在這裡，由 world_snapshot 與後續廣播送出。
    version 從 1 起算。格式有不相容變更時必須遞增。
    不相容指舊客戶端無法再讀：刪除或改名欄位，或欄位意義改了。
    只新增欄位不必遞增。
    """

    version: int
    pois: list[GameConfigPoi]
    poi_pick_radius: float
    agent_pick_radius: float
    need_low: int
    eat_restore: int
    items: list[GameConfigItem]


class GameConfigMessage(BaseModel):
    type: Literal["game_config"] = "game_config"
    data: GameConfig


class DialogueResultMessage(BaseModel):
    type: Literal["dialogue_result"] = "dialogue_result"
    client_seq: int
    speaker_id: str
    reply: str
    mood: str
    reason: str | None = None
    revealed_fact_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    note_ids: list[str] = Field(default_factory=list)
