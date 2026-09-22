from dataclasses import dataclass

from app.models.schemas import Position


@dataclass(frozen=True)
class POI:
    id: str
    name: str
    x: float
    y: float

    @property
    def position(self) -> Position:
        return Position(x=self.x, y=self.y)


POIS: dict[str, POI] = {
    "home": POI(id="home", name="Home", x=100.0, y=100.0),
    "cafe": POI(id="cafe", name="Cafe", x=400.0, y=250.0),
    "office": POI(id="office", name="Office", x=700.0, y=150.0),
    "park": POI(id="park", name="Park", x=500.0, y=500.0),
}
