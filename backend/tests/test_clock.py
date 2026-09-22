from app.config import GAME_MINUTES_PER_TICK, INITIAL_DAY, INITIAL_TIME
from app.simulation.clock import advance_clock
from app.simulation.world import World


def test_advance_minutes_into_next_hour() -> None:
    day, time = advance_clock(1, "08:59", 1)
    assert (day, time) == (1, "09:00")


def test_advance_23_59_to_next_day() -> None:
    day, time = advance_clock(1, "23:59", 1)
    assert (day, time) == (2, "00:00")


def test_advance_across_midnight_by_multiple_minutes() -> None:
    day, time = advance_clock(1, "23:30", 90)
    assert (day, time) == (2, "01:00")


def test_world_tick_advances_one_game_minute() -> None:
    world = World()
    world.tick()
    expected_day, expected_time = advance_clock(
        INITIAL_DAY,
        INITIAL_TIME,
        GAME_MINUTES_PER_TICK,
    )
    assert world.day == expected_day
    assert world.time == expected_time


def test_world_tick_rolls_over_to_next_day() -> None:
    world = World()
    world.day = 1
    world.time = "23:59"
    world.tick()
    assert world.day == 2
    assert world.time == "00:00"
