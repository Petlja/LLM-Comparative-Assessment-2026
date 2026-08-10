"""Construct balanced model-triplet assignments for survey participant groups."""

from dataclasses import dataclass
from itertools import combinations
from typing import Iterable

MODELS_PER_COMPARISON = 3


@dataclass(frozen=True)
class ComparisonAssignment:
    """The model triplet shown to one participant group for one test case."""

    case_key: str
    group: int
    models: tuple[str, str, str]


def build_model_triplets(model_ids: Iterable[str]) -> tuple[tuple[str, str, str], ...]:
    """Return every distinct three-model combination in deterministic order."""
    models = tuple(model_ids)
    if len(models) < MODELS_PER_COMPARISON:
        raise ValueError("At least three models are required for triplet comparisons.")
    if len(set(models)) != len(models):
        raise ValueError("Model identifiers must be unique.")

    return tuple(combinations(models, MODELS_PER_COMPARISON))


def build_group_assignments(
    case_keys: Iterable[str],
    model_ids: Iterable[str],
) -> tuple[ComparisonAssignment, ...]:
    """Assign rotated triplets so every group sees one triplet per test case.

    One group is created for each possible triplet. For any individual test case,
    the complete set of groups covers every triplet exactly once. Advancing the
    triplet by the test-case index prevents a group from receiving one fixed
    triplet throughout the survey.
    """
    cases = tuple(case_keys)
    if len(set(cases)) != len(cases):
        raise ValueError("Test case keys must be unique.")

    triplets = build_model_triplets(model_ids)
    assignments = []
    for case_index, case_key in enumerate(cases):
        for group_index in range(len(triplets)):
            triplet_index = (case_index + group_index) % len(triplets)
            assignments.append(
                ComparisonAssignment(
                    case_key=case_key,
                    group=group_index + 1,
                    models=triplets[triplet_index],
                )
            )
    return tuple(assignments)


def group_visibility_expression(group: int) -> str:
    """Return the SurveyJS expression selecting one numeric participant group."""
    if group < 1:
        raise ValueError("Group numbers start at 1.")
    return f"{{group}} = {group}"