from fastapi import APIRouter

from app import state
from app.config import SERVICE_NAME, VERSION, deployment_value
from app.models.schemas import Agent, HealthResponse, WorldEvent, WorldState

router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=SERVICE_NAME,
        version=VERSION,
        git_commit=deployment_value("GIT_COMMIT"),
        deployed_at=deployment_value("DEPLOYED_AT"),
    )


@router.get("/world", response_model=WorldState)
async def get_world() -> WorldState:
    return state.world.to_world_state()


@router.get("/agents", response_model=list[Agent])
async def get_agents() -> list[Agent]:
    return state.world.agent_list()


@router.get("/events", response_model=list[WorldEvent])
async def get_events() -> list[WorldEvent]:
    return state.world.recent_events()
