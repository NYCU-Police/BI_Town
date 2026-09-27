from dataclasses import dataclass

from app.config import ACTIVITY_MINUTES
from app.models.schemas import Position


@dataclass(frozen=True)
class Activity:
    id: str
    name: str
    minutes: int


def _activity(activity_id: str, name: str) -> Activity:
    return Activity(
        id=activity_id,
        name=name,
        minutes=ACTIVITY_MINUTES[activity_id],
    )


_HOME_ACTIVITIES = (
    _activity("cook", "煮飯"),
    _activity("rest", "休息"),
    _activity("sleep", "睡覺"),
)


@dataclass(frozen=True)
class POI:
    id: str
    name: str
    x: float
    y: float
    owner: str | None = None
    activities: tuple[Activity, ...] = ()

    @property
    def position(self) -> Position:
        return Position(x=self.x, y=self.y)


def activities_for(poi_id: str, actor_id: str) -> tuple[Activity, ...]:
    """Activities the actor can start here. Home chores are owner-only."""
    poi = POIS.get(poi_id)
    if poi is None:
        return ()
    if poi.owner not in (None, actor_id):
        return ()
    return poi.activities


# Coordinates are the ground in front of each door (feet), in pixels.
# Keep game/scripts/world.gd POIS in sync. The map is 60×40 tiles of 16px.
POIS: dict[str, POI] = {
    "mina_home": POI(
        id="mina_home",
        name="Mina 的家",
        x=72.0,
        y=112.0,
        owner="mina",
        activities=_HOME_ACTIVITIES,
    ),
    "alex_home": POI(
        id="alex_home",
        name="Alex 的家",
        x=232.0,
        y=112.0,
        owner="alex",
        activities=_HOME_ACTIVITIES,
    ),
    "rin_home": POI(
        id="rin_home",
        name="Rin 的家",
        x=392.0,
        y=112.0,
        owner="rin",
        activities=_HOME_ACTIVITIES,
    ),
    "cafe": POI(
        id="cafe",
        name="咖啡廳",
        x=584.0,
        y=112.0,
        activities=(
            _activity("order_coffee", "點咖啡"),
            _activity("read_book", "看書"),
            _activity("chat_staff", "跟店員聊天"),
        ),
    ),
    "store": POI(
        id="store",
        name="便利商店",
        x=808.0,
        y=112.0,
        activities=(_activity("shop", "買東西"),),
    ),
    "office": POI(
        id="office",
        name="辦公室",
        x=72.0,
        y=336.0,
        activities=(
            _activity("write_report", "寫報告"),
            _activity("sort_accounts", "整理帳目"),
            _activity("meeting", "開會"),
        ),
    ),
    "library": POI(
        id="library",
        name="圖書館",
        x=232.0,
        y=336.0,
        activities=(
            _activity("shelve_books", "整理書架"),
            _activity("borrow_book", "借書"),
            _activity("study", "自習"),
        ),
    ),
    "plaza": POI(
        id="plaza",
        name="廣場",
        x=584.0,
        y=336.0,
        activities=(
            _activity("read_board", "看公告欄"),
            _activity("wander", "閒逛"),
        ),
    ),
    "park": POI(
        id="park",
        name="公園",
        x=808.0,
        y=480.0,
        activities=(
            _activity("stroll", "散步"),
            _activity("sit_bench", "坐長椅"),
            _activity("take_photo", "拍照"),
        ),
    ),
}


def home_for(owner: str) -> POI:
    for poi in POIS.values():
        if poi.owner == owner:
            return poi
    raise KeyError(owner)
