from app.services.oven_engine import (
    Interval,
    Occupancy,
    RecipeDurations,
    build_occupancies,
    build_occupancies_from_ends,
    find_conflicts,
    next_free_window,
)


def test_build_occupancies_from_ends():
    occs = build_occupancies_from_ends(1, 9, 540, 580, 614)
    assert [o.phase for o in occs] == ["ferment", "bake"]
    assert occs[0].interval == Interval(540, 580)
    assert occs[1].interval == Interval(580, 614)


def test_build_occupancies_matches_recipe_ends():
    recipe = RecipeDurations(40, 35)
    assert build_occupancies(1, 9, 540, recipe) == build_occupancies_from_ends(1, 9, 540, 580, 615)


def test_half_open_no_touch_conflict():
    a = Occupancy(1, Interval(0, 30), "bake", 1)
    b = Occupancy(1, Interval(30, 60), "bake", 2)
    assert find_conflicts([a], [b]) == []


def test_overlap_detected():
    recipe = RecipeDurations(20, 30)
    cand = build_occupancies(1, 9, 10, recipe)
    existing = [Occupancy(1, Interval(25, 40), "bake", 1)]
    assert find_conflicts(existing, cand)


def test_next_free_window_after_busy():
    existing = [
        Occupancy(1, Interval(0, 40), "ferment", 1),
        Occupancy(1, Interval(40, 70), "bake", 1),
    ]
    w = next_free_window(existing, 1, duration=30, search_from=0)
    assert w == Interval(70, 100)


def test_next_free_in_gap():
    existing = [
        Occupancy(1, Interval(0, 20), "bake", 1),
        Occupancy(1, Interval(80, 100), "bake", 2),
    ]
    w = next_free_window(existing, 1, duration=30, search_from=0)
    assert w == Interval(20, 50)
