from app.models.schemas import Position
from app.simulation.fake_agent import distance
from app.simulation.poi import POIS
from app.simulation.world import World


def test_mina_schedule_at_08_00_targets_cafe() -> None:
    world = World()
    mina = world.agents["mina"]
    assert mina.location == "mina_home"
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
    assert alex.location == "alex_home"


def test_alex_leaves_for_cafe_at_08_30() -> None:
    world = World()
    world.time = "08:30"
    world.tick()
    alex = world.agents["alex"]
    assert alex.target_location == "cafe"
    assert alex.state == "walking"


def test_residents_start_at_their_own_homes() -> None:
    rules = World()
    assert rules.agents["mina"].location == "mina_home"
    assert rules.agents["mina"].position == POIS["mina_home"].position
    assert rules.agents["alex"].location == "alex_home"
    assert rules.agents["alex"].position == POIS["alex_home"].position

    llm = World(brain_mode="llm", decider=_stay)
    assert llm.agents["mina"].location == "mina_home"
    assert llm.agents["alex"].location == "alex_home"
    assert llm.agents["rin"].location == "rin_home"
    assert llm.agents["rin"].position == POIS["rin_home"].position


def test_evening_schedule_goes_to_each_residents_home() -> None:
    world = World()
    park = POIS["park"]
    for agent_id in ("mina", "alex"):
        agent = world.agents[agent_id]
        agent.location = "park"
        agent.target_location = "park"
        agent.position = park.position
    world.time = "20:00"
    world.tick()
    assert world.agents["mina"].target_location == "mina_home"
    assert world.agents["mina"].state == "walking"
    assert world.agents["alex"].location == "park"
    assert world.agents["alex"].state == "idle"

    world.time = "20:30"
    world.tick()
    assert world.agents["alex"].target_location == "alex_home"
    assert world.agents["alex"].state == "walking"


async def _stay(_messages: list, _schema: dict) -> str:
    return '{"action":"stay","target":"","say":"","thought":"待著"}'


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
