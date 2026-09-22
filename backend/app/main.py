import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router
from app.config import SERVICE_NAME, SIMULATION_LOOP_ENABLED, STATIC_WEB_DIR, VERSION
from app.simulation.loop import simulation_loop
from app.websocket.endpoint import router as ws_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

COOP_HEADER = "same-origin"
COEP_HEADER = "require-corp"


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


def _mount_godot_web(application: FastAPI) -> None:
    if not STATIC_WEB_DIR:
        logger.warning("STATIC_WEB_DIR unset; Godot web client will not be served")
        return
    static_dir = Path(STATIC_WEB_DIR)
    try:
        if not static_dir.is_dir():
            logger.warning(
                "STATIC_WEB_DIR does not exist (%s); Godot web client will not be served",
                static_dir,
            )
            return
        if not (static_dir / "index.html").is_file():
            logger.warning(
                "STATIC_WEB_DIR has no index.html (%s); Godot web client will not be served",
                static_dir,
            )
            return
        application.mount(
            "/",
            StaticFiles(directory=str(static_dir), html=True),
            name="godot_web",
        )
    except OSError:
        logger.warning(
            "Cannot read STATIC_WEB_DIR (%s); Godot web client will not be served",
            static_dir,
            exc_info=True,
        )
        return
    logger.info("Serving Godot web client from %s", static_dir.resolve())


app = FastAPI(title=SERVICE_NAME, version=VERSION, lifespan=lifespan)
app.include_router(api_router)
app.include_router(ws_router)


@app.middleware("http")
async def coop_coep_headers(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    response = await call_next(request)
    response.headers["Cross-Origin-Opener-Policy"] = COOP_HEADER
    response.headers["Cross-Origin-Embedder-Policy"] = COEP_HEADER
    return response


_mount_godot_web(app)
