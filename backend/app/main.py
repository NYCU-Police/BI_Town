import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router as api_router
from app.config import SERVICE_NAME, SIMULATION_LOOP_ENABLED, VERSION
from app.simulation.loop import simulation_loop
from app.websocket.endpoint import router as ws_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    logger.info("%s backend starting (v%s)", SERVICE_NAME, VERSION)
    task: asyncio.Task[None] | None = None
    if SIMULATION_LOOP_ENABLED:
        task = asyncio.create_task(simulation_loop())
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                logger.info("Simulation loop task cancelled")
            except Exception:
                logger.exception("Error while stopping simulation loop")
        logger.info("%s backend shutting down", SERVICE_NAME)


app = FastAPI(title=SERVICE_NAME, version=VERSION, lifespan=lifespan)
app.include_router(api_router)
app.include_router(ws_router)
