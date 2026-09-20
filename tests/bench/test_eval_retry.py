"""An infrastructure failure is retried, never written in as a verdict."""

from __future__ import annotations

from agent_bisect.bench.baselines import BaselineConfig
from agent_bisect.bench.eval_run import evaluate_dataset
from agent_bisect.bench.manifest import DatasetItem


def _item(index: int) -> DatasetItem:
    return DatasetItem(
        item_id=f"item-{index}", domain="airline", task_id=str(index), split="dev",
        base_run_id=f"b{index}", base_pass_rate=1.0, run_id=f"r{index}",
        faulted_pass_rate=0.0, planted_step=2, position_bucket="middle",
        fault_type="wrong_value", mutation={}, oracle={}, intervention={},
        seeds=[1], n_reruns=4,
    )


class _Reader:
    """Enough of a TapeReader for the retry loop; the judge is stubbed out."""

    def get_steps(self, run_id: str) -> list:
        return []


def _evaluate(items, failures, *, max_passes=3, tmp_path):
    """Drive evaluate_dataset with a task_text that fails N times per item."""
    remaining = dict(failures)
    seen: list[str] = []

    def task_text(domain: str, task_id: str) -> tuple[str, str]:
        item_id = f"item-{task_id}"
        seen.append(item_id)
        if remaining.get(item_id, 0) > 0:
            remaining[item_id] -= 1
            raise TimeoutError("litellm.Timeout: 504")
        raise LookupError("stop here: the judge is not the subject of this test")

    return evaluate_dataset(
        items,
        reader=_Reader(),  # type: ignore[arg-type]
        store=None,  # type: ignore[arg-type]
        judge_backend=None,  # type: ignore[arg-type]
        executor=None,  # type: ignore[arg-type]
        task_text=task_text,
        config=BaselineConfig(),
        seed=1,
        runs_dir=tmp_path,
        max_passes=max_passes,
        sleep=lambda _s: None,
    ), seen


def test_a_failing_item_is_retried_across_passes(tmp_path):
    # Arrange: item-0 fails once, then fails differently (LookupError) forever
    items = [_item(0)]

    # Act
    run, seen = _evaluate(items, {"item-0": 1}, tmp_path=tmp_path)

    # Assert: it was attempted on more than one pass
    assert seen.count("item-0") > 1
    assert run.n_failed_items == 1


def test_the_run_is_incomplete_while_any_item_has_no_verdict(tmp_path):
    # Arrange / Act
    run, _ = _evaluate([_item(0)], {"item-0": 99}, tmp_path=tmp_path)

    # Assert
    assert run.complete is False


def test_a_failed_item_contributes_no_outcome_rows(tmp_path):
    """The bug that made a dev run report 0.0 accuracy for every method."""
    # Arrange / Act
    run, _ = _evaluate([_item(0), _item(1)], {"item-0": 99, "item-1": 99},
                       tmp_path=tmp_path)

    # Assert
    assert run.outcomes == []


def test_passes_stop_at_the_configured_limit(tmp_path):
    # Arrange / Act
    _, seen = _evaluate([_item(0)], {"item-0": 99}, max_passes=2, tmp_path=tmp_path)

    # Assert
    assert seen.count("item-0") == 2
