import asyncio
import logging

from app import state
from app.config import SIMULATION_TICK_SECONDS
from app.simulation.llm_session import decision_worker
from app.simulation.world import TickResult
from app.websocket.broadcast import broadcast_changes

logger = logging.getLogger(__name__)


async def broadcast_tick(result: TickResult) -> None:
    await broadcast_changes(result.events, result.changed_agents)


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
