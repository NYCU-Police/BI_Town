from app.models.schemas import Position
from app.simulation.fake_agent import distance
from app.simulation.poi import POIS
from app.simulation.world import World


def test_mina_schedule_at_08_00_targets_cafe() -> None:
    world = World()
    mina = world.agents["mina"]
    assert mina.location == "home"
    assert mina.state == "idle"

    world.tick()

    mina = world.agents["mina"]
    assert mina.target_location == "cafe"
    assert mina.state == "walking"


def test_tick_moves_agent_closer_to_target() -> None:
    world = World()
    cafe = POIS["cafe"]
    before = distance(world.agents["mina"].position, cafe.position)

    world.tick()

    after = distance(world.agents["mina"].position, cafe.position)
    assert after < before


def test_alex_does_not_leave_at_08_00() -> None:
    world = World()
    world.tick()
    alex = world.agents["alex"]
    assert alex.state == "idle"
    assert alex.location == "home"


def test_alex_leaves_for_cafe_at_08_30() -> None:
    world = World()
    world.time = "08:30"
    world.tick()
    alex = world.agents["alex"]
    assert alex.target_location == "cafe"
    assert alex.state == "walking"


def test_agent_arrives_and_becomes_idle() -> None:
    world = World()
    cafe = POIS["cafe"]
    mina = world.agents["mina"]
    mina.position = Position(x=cafe.x - 5.0, y=cafe.y)
    mina.target_location = "cafe"
    mina.state = "walking"

    world.tick()

    mina = world.agents["mina"]
    assert mina.state == "idle"
    assert mina.location == "cafe"
    assert mina.position.x == cafe.x
    assert mina.position.y == cafe.y
