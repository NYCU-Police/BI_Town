"""Rules that stay fixed for one round. Rebuilt on every connection."""

from app import config
from app.models.schemas import GameConfig, GameConfigItem, GameConfigPoi
from app.simulation.poi import POIS


def build_game_config() -> GameConfig:
    known = set(config.FOOD_ITEMS) | set(config.TOOL_IDS) | {config.PARK_PRODUCT_ID}
    display = dict(config.ITEM_DISPLAY)
    if set(display) != known:
        raise RuntimeError("ITEM_DISPLAY does not match the item ids in config")
    return GameConfig(
        version=config.GAME_CONFIG_VERSION,
        pois=[
            GameConfigPoi(id=poi.id, name=poi.name, x=poi.x, y=poi.y)
            for poi in POIS.values()
        ],
        poi_pick_radius=config.POI_PICK_RADIUS,
        agent_pick_radius=config.AGENT_PICK_RADIUS,
        need_low=int(config.NEED_HUNGRY),
        eat_restore=int(config.EAT_FULLNESS_RESTORE),
        items=[
            GameConfigItem(
                id=item_id,
                name=name,
                food=item_id in config.FOOD_ITEMS,
            )
            for item_id, name in config.ITEM_DISPLAY
        ],
    )
