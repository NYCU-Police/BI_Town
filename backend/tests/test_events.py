from app.config import MAX_WORLD_EVENTS
from app.models.schemas import WorldEvent
from app.simulation.poi import POIS
from app.simulation.world import World


def test_leaving_home_creates_left_event() -> None:
    world = World()
    world.tick()
    events = world.recent_events()
    assert len(events) == 1
    assert events[0] == WorldEvent(
        timestamp="08:00",
        agent_id="mina",
        event="left",
        location="home",
    )


def test_arrival_creates_entered_event() -> None:
    world = World()
    cafe = POIS["cafe"]
    mina = world.agents["mina"]
    mina.position = mina.position.model_copy(update={"x": cafe.x - 5.0, "y": cafe.y})
    mina.target_location = "cafe"
    mina.state = "walking"

    world.tick()

    entered = [
        event
        for event in world.recent_events()
        if event.event == "entered" and event.agent_id == "mina"
    ]
    assert entered
    assert entered[0].location == "cafe"
    assert entered[0].timestamp == "08:00"


def test_events_capped_at_max() -> None:
    world = World()
    for index in range(MAX_WORLD_EVENTS + 1):
        world.add_event(
            WorldEvent(
                timestamp="08:00",
                agent_id="mina",
                event="left",
                location=f"loc-{index}",
            )
        )

    events = world.recent_events()
    assert len(events) == MAX_WORLD_EVENTS
    assert events[0].location == "loc-1"
    assert events[-1].location == f"loc-{MAX_WORLD_EVENTS}"
