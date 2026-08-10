from collections import Counter
from itertools import combinations

import pytest

from llm_assessment_2026.comparison_design import (
    build_group_assignments,
    build_model_triplets,
    group_visibility_expression,
)


def test_five_models_produce_ten_triplets() -> None:
    triplets = build_model_triplets(["a", "b", "c", "d", "e"])

    assert len(triplets) == 10
    assert len(set(triplets)) == 10


def test_each_case_balances_all_triplets_and_model_pairs() -> None:
    models = ["a", "b", "c", "d", "e"]
    assignments = build_group_assignments(["case-1", "case-2"], models)

    expected_triplets = set(combinations(models, 3))
    for case_key in ["case-1", "case-2"]:
        case_assignments = [item for item in assignments if item.case_key == case_key]
        assert {item.group for item in case_assignments} == set(range(1, 11))
        assert {item.models for item in case_assignments} == expected_triplets

        pair_counts = Counter(
            pair
            for item in case_assignments
            for pair in combinations(item.models, 2)
        )
        assert set(pair_counts.values()) == {3}


def test_triplets_rotate_between_cases_within_a_group() -> None:
    assignments = build_group_assignments(
        ["case-1", "case-2"],
        ["a", "b", "c", "d", "e"],
    )

    group_one = [item.models for item in assignments if item.group == 1]
    assert group_one == [("a", "b", "c"), ("a", "b", "d")]


def test_group_visibility_uses_simple_survey_numeric_variable() -> None:
    assert group_visibility_expression(3) == "{group} = 3"


@pytest.mark.parametrize(
    "models",
    [
        ["a", "b"],
        ["a", "b", "a"],
    ],
)
def test_invalid_model_sets_are_rejected(models: list[str]) -> None:
    with pytest.raises(ValueError):
        build_model_triplets(models)