"""Oven scheduling with half-open ferment+bake intervals and next free window."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Interval:
    start: int  # minutes from day origin
    end: int  # exclusive

    def overlaps(self, other: "Interval") -> bool:
        return self.start < other.end and other.start < self.end


@dataclass(frozen=True)
class RecipeDurations:
    ferment_min: int
    bake_min: int

    @property
    def total(self) -> int:
        return self.ferment_min + self.bake_min


@dataclass(frozen=True)
class Occupancy:
    oven_id: int
    interval: Interval
    phase: str  # ferment | bake
    batch_id: int


def recipe_ends(start_min: int, recipe: RecipeDurations) -> tuple[int, int]:
    """按产品时长算出的 (发酵止, 烘烤止)，仅用于创建时写入和一致性核对。"""
    ferment_end = start_min + recipe.ferment_min
    return ferment_end, ferment_end + recipe.bake_min


def build_occupancies(
    oven_id: int,
    batch_id: int,
    start_min: int,
    recipe: RecipeDurations,
) -> list[Occupancy]:
    ferment_end, bake_end = recipe_ends(start_min, recipe)
    return build_stored_occupancies(oven_id, batch_id, start_min, ferment_end, bake_end)


def build_stored_occupancies(
    oven_id: int,
    batch_id: int,
    start_min: int,
    ferment_end_min: int,
    bake_end_min: int,
) -> list[Occupancy]:
    """按批次落库的止点构建占炉区间——已存在批次的唯一读取入口。"""
    return [
        Occupancy(oven_id, Interval(start_min, ferment_end_min), "ferment", batch_id),
        Occupancy(oven_id, Interval(ferment_end_min, bake_end_min), "bake", batch_id),
    ]


def find_conflicts(existing: list[Occupancy], candidates: list[Occupancy]) -> list[tuple[Occupancy, Occupancy]]:
    hits: list[tuple[Occupancy, Occupancy]] = []
    for cand in candidates:
        for ex in existing:
            if ex.oven_id != cand.oven_id:
                continue
            if ex.interval.overlaps(cand.interval):
                hits.append((ex, cand))
    return hits


def next_free_window(
    existing: list[Occupancy],
    oven_id: int,
    duration: int,
    search_from: int = 0,
    search_to: int = 24 * 60,
) -> Interval | None:
    """Find earliest half-open [start, start+duration) free on oven."""
    if duration <= 0:
        return None
    busy = sorted(
        [o.interval for o in existing if o.oven_id == oven_id],
        key=lambda i: i.start,
    )
    cursor = search_from
    for iv in busy:
        if iv.end <= cursor:
            continue
        if iv.start >= cursor + duration:
            end = cursor + duration
            if end <= search_to:
                return Interval(cursor, end)
            return None
        cursor = max(cursor, iv.end)
    if cursor + duration <= search_to:
        return Interval(cursor, cursor + duration)
    return None
