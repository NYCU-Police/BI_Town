from dataclasses import dataclass

from app.models.schemas import Position


@dataclass(frozen=True)
class POI:
    id: str
    name: str
    x: float
    y: float
    owner: str | None = None

    @property
    def position(self) -> Position:
        return Position(x=self.x, y=self.y)


# Coordinates are the ground in front of each door (feet), in pixels.
# Keep game/scripts/world.gd POIS in sync. The map is 60×40 tiles of 16px.
POIS: dict[str, POI] = {
    "mina_home": POI(
        id="mina_home", name="Mina 的家", x=72.0, y=112.0, owner="mina"
    ),
    "alex_home": POI(
        id="alex_home", name="Alex 的家", x=232.0, y=112.0, owner="alex"
    ),
    "rin_home": POI(
        id="rin_home", name="Rin 的家", x=392.0, y=112.0, owner="rin"
    ),
    "cafe": POI(id="cafe", name="咖啡廳", x=584.0, y=112.0),
    "store": POI(id="store", name="便利商店", x=808.0, y=112.0),
    "office": POI(id="office", name="辦公室", x=72.0, y=336.0),
    "library": POI(id="library", name="圖書館", x=232.0, y=336.0),
    "plaza": POI(id="plaza", name="廣場", x=584.0, y=336.0),
    "park": POI(id="park", name="公園", x=808.0, y=480.0),
}


def home_for(owner: str) -> POI:
    for poi in POIS.values():
        if poi.owner == owner:
            return poi
    raise KeyError(owner)
