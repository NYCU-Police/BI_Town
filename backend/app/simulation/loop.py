import asyncio
import logging

from app import state
from app.config import SIMULATION_TICK_SECONDS
from app.models.schemas import AgentUpdateData, AgentUpdateMessage, WorldEventMessage
from app.simulation.llm_session import decision_worker
from app.simulation.world import TickResult
from app.websocket.manager import manager

logger = logging.getLogger(__name__)


async def broadcast_tick(result: TickResult) -> None:
    message = AgentUpdateMessage(
        data=AgentUpdateData(
            day=state.world.day,
            time=state.world.time,
            agents=result.changed_agents,
        )
    )
    await manager.broadcast(message.model_dump())
    for event in result.events:
        payload = WorldEventMessage(data=event).model_dump(exclude_none=True)
        await manager.broadcast(payload)


async def simulation_loop() -> None:
    logger.info("Simulation loop started")
    worker: asyncio.Task[None] | None = None
    if state.world.llm is not None:
        worker = asyncio.create_task(decision_worker(state.world.llm))
    try:
        while True:
            await asyncio.sleep(SIMULATION_TICK_SECONDS)
            try:
                result = state.world.tick()
                await broadcast_tick(result)
            except Exception:
                logger.exception("Simulation tick failed")
    except asyncio.CancelledError:
        logger.info("Simulation loop cancelled")
        raise
    finally:
        if worker is not None:
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                logger.info("LLM decision worker cancelled")
