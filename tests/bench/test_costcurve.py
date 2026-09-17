"""Re-deriving accuracy at smaller N and m from the re-runs already bought."""

from __future__ import annotations

import pytest
from agent_bisect.attribution.estimate import SequentialConfig
from agent_bisect.bench.costcurve import (
    RecordedSampler,
    SamplerExhaustedError,
    derive_curve,
)


def _reruns(step_probs: dict[int, list[bool]], control: list[bool], fork_step: int):
    rows = [
        {"rerun_id": f"c{fork_step}-{i}", "arm": "control", "step": fork_step,
         "seed": i, "passed": passed, "n_steps": 12, "calls": 10}
        for i, passed in enumerate(control)
    ]
    for step, outcomes in step_probs.items():
        rows.extend(
            {"rerun_id": f"t{step}-{i}", "arm": "treated", "step": step,
             "seed": i, "passed": passed, "n_steps": 12, "calls": 10}
            for i, passed in enumerate(outcomes)
        )
    return rows


def _document(*, tested=(3, 5, 7), planted_hit=5, fork_step=3):
    hit = [True] * 16
    miss = [False] * 16
    return {
        "item_id": "item-1",
        "run_id": "run-1",
        "tested_steps": list(tested),
        "cost": {"judge_calls": 1, "replay_calls": 640, "total_calls": 641},
        "estimate": {"control_mode": "shared", "control_fork_step": fork_step},
        "reruns": _reruns(
            {step: (hit if step == planted_hit else miss) for step in tested},
            [False] * 16,
            fork_step,
        ),
    }


# ---- RecordedSampler ----


def test_serves_the_recorded_outcomes_in_order():
    # Arrange
    sampler = RecordedSampler(_document()["reruns"])

    # Act
    first = sampler.sample(5, "treated", 4, seed=0)
    second = sampler.sample(5, "treated", 4, seed=0)

    # Assert
    assert first == (True, True, True, True)
    assert second == (True, True, True, True)


def test_running_out_of_recorded_draws_is_an_error_not_a_guess():
    # Arrange
    sampler = RecordedSampler(_document()["reruns"])

    # Act / Assert
    with pytest.raises(SamplerExhaustedError, match="step 5"):
        sampler.sample(5, "treated", 20, seed=0)


def test_a_control_drawn_at_another_fork_step_is_reused_and_flagged():
    # Arrange: the control was drawn at step 3, the sampler is asked at 5
    sampler = RecordedSampler(_document()["reruns"])

    # Act
    outcomes = sampler.sample(5, "control", 4, seed=0)

    # Assert
    assert outcomes == (False, False, False, False)
    assert sampler.control_reused is True


def test_a_control_at_its_own_fork_step_is_not_flagged_as_reused():
    # Arrange
    sampler = RecordedSampler(_document()["reruns"])

    # Act
    sampler.sample(3, "control", 4, seed=0)

    # Assert
    assert sampler.control_reused is False


def test_an_unknown_treated_step_is_an_error():
    # Arrange
    sampler = RecordedSampler(_document()["reruns"])

    # Act / Assert
    with pytest.raises(SamplerExhaustedError, match="step 99"):
        sampler.sample(99, "treated", 1, seed=0)


# ---- derive_curve ----


def _labels():
    return {"item-1": 5, "item-2": 5}


def _documents():
    first = _document()
    second = dict(_document(), item_id="item-2", run_id="run-2")
    return {"item-1": first, "item-2": second}


def test_the_curve_covers_every_requested_n_and_m():
    # Arrange / Act
    points = derive_curve(
        _documents(), _labels(), n_values=(4, 8, 16), m_values=(1, 3),
        config=SequentialConfig(),
    )

    # Assert
    assert {(point.n, point.m) for point in points} == {
        (4, 1), (4, 3), (8, 1), (8, 3), (16, 1), (16, 3)
    }


def test_a_point_that_needed_no_new_reruns_is_marked_derived():
    # Arrange / Act
    points = derive_curve(
        _documents(), _labels(), n_values=(8,), m_values=(3,), config=SequentialConfig()
    )

    # Assert
    assert points[0].source == "derived"


def test_the_primary_configuration_is_marked_measured():
    # Arrange / Act
    points = derive_curve(
        _documents(), _labels(), n_values=(16,), m_values=(3,), config=SequentialConfig(),
        primary=(16, 3),
    )

    # Assert
    assert points[0].source == "measured"


def test_accuracy_at_m_one_drops_when_the_culprit_is_not_first():
    # Arrange: tested order is (3, 5, 7); the culprit is 5, so m=1 misses it
    documents = _documents()

    # Act
    at_one = derive_curve(
        documents, _labels(), n_values=(16,), m_values=(1,), config=SequentialConfig()
    )[0]
    at_three = derive_curve(
        documents, _labels(), n_values=(16,), m_values=(3,), config=SequentialConfig()
    )[0]

    # Assert
    assert at_one.accuracy == 0.0
    assert at_three.accuracy == 1.0


def test_every_point_reports_how_many_items_it_could_be_derived_from():
    # Arrange / Act
    points = derive_curve(
        _documents(), _labels(), n_values=(16,), m_values=(3,), config=SequentialConfig()
    )

    # Assert
    assert points[0].n_items == 2


def test_an_item_whose_draws_run_out_is_excluded_and_counted():
    # Arrange: one item has only 4 treated draws per step
    short = _document()
    short["item_id"] = "item-2"
    short["reruns"] = [row for row in short["reruns"] if row["seed"] < 4]
    documents = {"item-1": _document(), "item-2": short}

    # Act
    point = derive_curve(
        documents, _labels(), n_values=(16,), m_values=(3,), config=SequentialConfig()
    )[0]

    # Assert
    assert point.n_items == 1
    assert "item-2" in point.note


def test_the_mean_call_cost_scales_with_the_reruns_actually_used():
    # Arrange / Act
    cheap = derive_curve(
        _documents(), _labels(), n_values=(4,), m_values=(1,), config=SequentialConfig()
    )[0]
    dear = derive_curve(
        _documents(), _labels(), n_values=(16,), m_values=(3,), config=SequentialConfig()
    )[0]

    # Assert
    assert cheap.mean_calls < dear.mean_calls


def test_the_derivation_uses_the_nominal_boundary_and_says_so():
    # Arrange / Act
    point = derive_curve(
        _documents(), _labels(), n_values=(8,), m_values=(3,), config=SequentialConfig()
    )[0]

    # Assert
    assert point.efficacy_boundary == "none"


def test_a_curve_over_no_items_is_refused():
    # Arrange / Act / Assert
    with pytest.raises(ValueError, match="no items"):
        derive_curve({}, {}, n_values=(16,), m_values=(3,), config=SequentialConfig())
