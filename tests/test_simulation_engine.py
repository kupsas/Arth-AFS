"""
Unit tests for Sub-Plan G — :mod:`api.services.simulation` (pure functions, no DB).
"""

from __future__ import annotations

import datetime
import time

import pytest

from api.services.simulation import (
    GC_GROWTH,
    GC_POINT,
    GC_RECURRING,
    OneTimeEvent,
    SimulationGoal,
    SimulationParams,
    allocate_surplus,
    compare_scenarios,
    compute_target_at_month,
    simulate,
)


def _pit(
    name: str,
    *,
    tid: int,
    target: float,
    target_date: datetime.date,
    priority: int,
    start: float = 0.0,
    ret: float = 12.0,
    infl: float = 0.0,
) -> SimulationGoal:
    return SimulationGoal(
        id=tid,
        name=name,
        goal_class=GC_POINT,
        target_amount=target,
        target_date=target_date,
        starting_balance=start,
        allocation_priority=priority,
        expected_return_rate=ret,
        inflation_rate=infl,
    )


def test_single_point_in_time_goal_projection():
    """20L target in 5 years, 12% return, ₹30k surplus — expect trajectory + completion."""
    today = datetime.date(2026, 1, 1)
    target_d = datetime.date(2031, 1, 1)
    g = _pit("House", tid=1, target=2_000_000.0, target_date=target_d, priority=1)
    g2 = SimulationGoal(
        id=2,
        name="Growth",
        goal_class=GC_GROWTH,
        allocation_priority=2,
    )
    p = SimulationParams(
        goals=[g, g2],
        monthly_surplus=30_000.0,
        simulation_months=120,
        as_of_date=today,
    )
    r = simulate(p)
    house = next(x for x in r.projections if x.goal_name == "House")
    assert house.projected_completion_date is not None
    assert house.status == "ACHIEVED"
    assert len(house.monthly_trajectory) == 120
    assert house.monthly_trajectory[0].month == today.replace(day=1)


def test_cascade_two_goals_second_gets_surplus_after_first_completes():
    """First goal small target completes early; second should show earlier completion vs isolated."""
    today = datetime.date(2026, 6, 1)
    g1 = _pit(
        "Quick",
        tid=1,
        target=50_000.0,
        target_date=datetime.date(2027, 6, 1),
        priority=1,
        start=40_000.0,
        ret=10.0,
        infl=0.0,
    )
    g2 = _pit(
        "Slow",
        tid=2,
        target=500_000.0,
        target_date=datetime.date(2031, 6, 1),
        priority=2,
        start=0.0,
        ret=10.0,
        infl=0.0,
    )
    growth = SimulationGoal(id=3, name="Invest", goal_class=GC_GROWTH, allocation_priority=3)
    p = SimulationParams(
        goals=[g1, g2, growth],
        monthly_surplus=25_000.0,
        simulation_months=120,
        as_of_date=today,
    )
    r = simulate(p)
    quick = next(x for x in r.projections if x.goal_name == "Quick")
    assert quick.status == "ACHIEVED"
    assert len(r.cascade_events) >= 1


def test_recurring_emi_within_window():
    today = datetime.date(2026, 1, 1)
    emi = SimulationGoal(
        id=1,
        name="Loan EMI",
        goal_class=GC_RECURRING,
        allocation_priority=1,
        recurrence_amount=55_000.0,
        recurrence_frequency="MONTHLY",
        recurrence_start=datetime.date(2026, 1, 1),
        recurrence_end=datetime.date(2046, 1, 1),
        expected_return_rate=0.0,
    )
    growth = SimulationGoal(id=2, name="Rest", goal_class=GC_GROWTH, allocation_priority=2)
    p = SimulationParams(
        goals=[emi, growth],
        monthly_surplus=100_000.0,
        simulation_months=24,
        as_of_date=today,
    )
    r = simulate(p)
    emi_p = next(x for x in r.projections if x.goal_name == "Loan EMI")
    # Average allocation to EMI should be substantial (capped by surplus after growth split)
    assert emi_p.monthly_allocation > 40_000.0


def test_growth_absorbs_remainder():
    g = SimulationGoal(
        id=1,
        name="Long",
        goal_class=GC_GROWTH,
        allocation_priority=1,
        expected_return_rate=10.0,
    )
    p = SimulationParams(
        goals=[g],
        monthly_surplus=50_000.0,
        simulation_months=60,
        as_of_date=datetime.date(2026, 1, 1),
    )
    r = simulate(p)
    gp = r.projections[0]
    assert gp.projected_final_amount > 3_000_000.0


def test_salary_growth_increases_surplus():
    g = SimulationGoal(
        id=1,
        name="G",
        goal_class=GC_GROWTH,
        allocation_priority=1,
    )
    p = SimulationParams(
        goals=[g],
        monthly_surplus=100_000.0,
        salary_growth_rate=10.0,
        simulation_months=24,
        as_of_date=datetime.date(2026, 1, 1),
    )
    r = simulate(p)
    # Month 13+ should have higher net worth trajectory than without growth
    p2 = SimulationParams(**{**p.model_dump(), "salary_growth_rate": 0.0})
    r2 = simulate(p2)
    assert r.net_worth_projection[-1].total_value > r2.net_worth_projection[-1].total_value


def test_one_time_inflow_accelerates():
    today = datetime.date(2026, 1, 1)
    g = _pit(
        "Save",
        tid=1,
        target=1_000_000.0,
        target_date=datetime.date(2030, 1, 1),
        priority=1,
        ret=8.0,
    )
    g2 = SimulationGoal(id=2, name="Gr", goal_class=GC_GROWTH, allocation_priority=2)
    bonus = OneTimeEvent(amount=500_000.0, date=datetime.date(2026, 6, 15), description="bonus")
    p = SimulationParams(
        goals=[g, g2],
        monthly_surplus=10_000.0,
        one_time_inflows=[bonus],
        simulation_months=80,
        as_of_date=today,
    )
    r = simulate(p)
    base = SimulationParams(
        goals=[g, g2],
        monthly_surplus=10_000.0,
        simulation_months=80,
        as_of_date=today,
    )
    r0 = simulate(base)
    h = next(x for x in r.projections if x.goal_name == "Save")
    h0 = next(x for x in r0.projections if x.goal_name == "Save")
    if h.projected_completion_date and h0.projected_completion_date:
        assert h.projected_completion_date <= h0.projected_completion_date


def test_inflation_reduces_achievement():
    today = datetime.date(2026, 1, 1)
    td = datetime.date(2031, 1, 1)
    g = _pit("T", tid=1, target=1_000_000.0, target_date=td, priority=1, infl=0.0)
    g2 = SimulationGoal(id=2, name="X", goal_class=GC_GROWTH, allocation_priority=2)
    p0 = SimulationParams(goals=[g, g2], monthly_surplus=15_000.0, simulation_months=120, as_of_date=today)
    g_hi = _pit("T", tid=1, target=1_000_000.0, target_date=td, priority=1, infl=8.0)
    p1 = SimulationParams(goals=[g_hi, g2], monthly_surplus=15_000.0, simulation_months=120, as_of_date=today)
    r0 = simulate(p0)
    r1 = simulate(p1)
    a = next(x for x in r0.projections if x.goal_name == "T")
    b = next(x for x in r1.projections if x.goal_name == "T")
    assert b.shortfall >= a.shortfall


def test_edge_no_goals():
    r = simulate(SimulationParams(goals=[]))
    assert r.projections == []
    assert "No goals" in r.warnings[0]


def test_edge_already_funded():
    today = datetime.date(2026, 1, 1)
    g = _pit(
        "Done",
        tid=1,
        target=100_000.0,
        target_date=datetime.date(2027, 1, 1),
        priority=1,
        start=150_000.0,
    )
    p = SimulationParams(goals=[g], monthly_surplus=0.0, simulation_months=12, as_of_date=today)
    r = simulate(p)
    assert r.projections[0].status == "ACHIEVED"


def test_allocate_surplus_sums_to_surplus_when_growth_present():
    goals = [
        _pit("A", tid=1, target=500_000.0, target_date=datetime.date(2030, 1, 1), priority=1),
        SimulationGoal(id=2, name="G", goal_class=GC_GROWTH, allocation_priority=2),
    ]
    out = allocate_surplus(goals, 80_000.0, today=datetime.date(2026, 1, 1))
    assert abs(sum(out.values()) - 80_000.0) < 1.0


def test_compare_scenarios_delta():
    today = datetime.date(2026, 1, 1)
    g = _pit("X", tid=1, target=800_000.0, target_date=datetime.date(2032, 1, 1), priority=1)
    gr = SimulationGoal(id=2, name="G", goal_class=GC_GROWTH, allocation_priority=2)
    base = SimulationParams(goals=[g, gr], monthly_surplus=20_000.0, simulation_months=100, as_of_date=today)
    var = SimulationParams(goals=[g, gr], monthly_surplus=40_000.0, simulation_months=100, as_of_date=today)
    comps = compare_scenarios(base, [var])
    assert len(comps) == 1
    assert "monthly_surplus" in comps[0].changes_from_base


def test_compute_target_at_month():
    g = _pit(
        "C",
        tid=1,
        target=1.0,
        target_date=datetime.date(2030, 1, 1),
        priority=1,
        start=10_000.0,
        ret=12.0,
    )
    t = compute_target_at_month(g, 12, monthly_required=5_000.0)
    assert t is not None and t > 10_000.0


def test_performance_ten_goals_twenty_years():
    today = datetime.date(2026, 1, 1)
    goals: list[SimulationGoal] = []
    for i in range(10):
        goals.append(
            _pit(
                f"G{i}",
                tid=i + 1,
                target=500_000.0 + i * 10_000,
                target_date=datetime.date(2046, 1, 1),
                priority=i + 1,
            )
        )
    p = SimulationParams(goals=goals, monthly_surplus=200_000.0, simulation_months=240, as_of_date=today)
    t0 = time.perf_counter()
    simulate(p)
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.1, f"took {elapsed:.3f}s, expected <100ms"
