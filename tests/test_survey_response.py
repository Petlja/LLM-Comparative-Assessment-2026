import json
from pathlib import Path
from runpy import run_path

import pytest


_module = run_path(
    str(Path(__file__).parents[1] / "suvrey-analisys" / "survey_responce.py")
)
rank_llms_by_category_borda = _module["rank_llms_by_category_borda"]
rank_llms_by_category_pl = _module["rank_llms_by_category_pl"]


@pytest.fixture
def survey_path(tmp_path: Path) -> Path:
    path = tmp_path / "survey.json"
    path.write_text(json.dumps({
        "pages": [{"elements": [{
            "type": "matrixdropdown",
            "name": "ranking",
            "columns": [{"choices": [
                {"value": model} for model in ("model-c", "model-b", "model-a")
            ]}],
            "rows": [
                {"value": "q1", "text": "Accuracy"},
                {"value": "q2", "text": "Clarity"},
                {"value": "q3", "text": "Unused"},
            ],
        }]}],
    }), encoding="utf-8")
    return path


def test_borda_averages_categories_and_ties(survey_path: Path) -> None:
    responses = [
        {"answers": {
            "comment": "Ignored",
            "ranking": {
                "q1": {"best": "model-a", "worst": "model-c"},
                "q2": {"best": "model-c", "worst": "model-a"},
            },
        }},
        {"answers": {"ranking": {
            "q1": {"best": "model-b", "worst": "model-c"},
        }}},
    ]

    assert rank_llms_by_category_borda(responses, survey_path) == {
        "Accuracy": [
            {"rank": 1, "model": "model-a", "score": 4.0, "answer_count": 2},
            {"rank": 2, "model": "model-b", "score": 4.0, "answer_count": 2},
            {"rank": 3, "model": "model-c", "score": 1.0, "answer_count": 2},
        ],
        "Clarity": [
            {"rank": 1, "model": "model-c", "score": 5, "answer_count": 1},
            {"rank": 2, "model": "model-b", "score": 3, "answer_count": 1},
            {"rank": 3, "model": "model-a", "score": 1, "answer_count": 1},
        ],
    }


@pytest.mark.parametrize("selection", [
    {},
    {"best": "model-a"},
    {"worst": "model-c"},
    {"best": "model-a", "worst": "model-a"},
    {"best": "unknown", "worst": "model-c"},
])
def test_borda_invalid_rankings(survey_path: Path, selection: dict[str, str]) -> None:
    responses = [{"answers": {"ranking": {
        "q1": selection,
        "q2": {"best": "model-a", "worst": "model-c"},
    }}}]

    with pytest.raises(ValueError, match="Invalid ranking in ranking, q1"):
        rank_llms_by_category_borda(responses, survey_path)

    assert rank_llms_by_category_borda(
        responses, survey_path, skip_incomplete=True,
    ) == {"Clarity": [
        {"rank": 1, "model": "model-a", "score": 5, "answer_count": 1},
        {"rank": 2, "model": "model-b", "score": 3, "answer_count": 1},
        {"rank": 3, "model": "model-c", "score": 1, "answer_count": 1},
    ]}


def test_borda_averages_per_model_appearance(survey_path: Path) -> None:
    survey = json.loads(survey_path.read_text(encoding="utf-8"))
    matrix = survey["pages"][0]["elements"][0]
    survey["pages"].append({"elements": [{
        **matrix,
        "name": "other_ranking",
        "columns": [{"choices": [
            {"value": model} for model in ("model-a", "model-b", "model-d")
        ]}],
    }]})
    survey_path.write_text(json.dumps(survey), encoding="utf-8")
    responses = [
        {"answers": {"ranking": {
            "q1": {"best": "model-a", "worst": "model-c"},
        }}},
        {"answers": {"ranking": {
            "q1": {"best": "model-a", "worst": "model-c"},
        }}},
        {"answers": {"other_ranking": {
            "q1": {"best": "model-d", "worst": "model-a"},
        }}},
        {"answers": {"ranking": {"q1": {"best": "model-a"}}}},
    ]

    assert rank_llms_by_category_borda(
        responses, survey_path, skip_incomplete=True,
    ) == {"Accuracy": [
        {"rank": 1, "model": "model-d", "score": 5.0, "answer_count": 1},
        {"rank": 2, "model": "model-a", "score": pytest.approx(11 / 3), "answer_count": 3},
        {"rank": 3, "model": "model-b", "score": 3.0, "answer_count": 3},
        {"rank": 4, "model": "model-c", "score": 1.0, "answer_count": 2},
    ]}


@pytest.mark.parametrize("rank_models", [
    rank_llms_by_category_borda,
    rank_llms_by_category_pl,
])
def test_answer_counts_per_model_and_category(survey_path: Path, rank_models) -> None:
    survey = json.loads(survey_path.read_text(encoding="utf-8"))
    matrix = survey["pages"][0]["elements"][0]
    survey["pages"].append({"elements": [{
        **matrix,
        "name": "other_ranking",
        "columns": [{"choices": [
            {"value": model} for model in ("model-a", "model-b", "model-d")
        ]}],
    }]})
    survey_path.write_text(json.dumps(survey), encoding="utf-8")
    responses = [{"answers": {
        "ranking": {
            "q1": {"best": "model-a", "worst": "model-c"},
            "q2": {"best": "model-c", "worst": "model-a"},
        },
        "other_ranking": {
            "q1": {"best": "model-d", "worst": "model-a"},
            "q2": {"best": "model-d"},
        },
    }}]

    results = rank_models(responses, survey_path, skip_incomplete=True)

    assert {
        category: {row["model"]: row["answer_count"] for row in rows}
        for category, rows in results.items()
    } == {
        "Accuracy": {"model-a": 2, "model-b": 2, "model-c": 1, "model-d": 1},
        "Clarity": {"model-a": 1, "model-b": 1, "model-c": 1},
    }


def test_borda_empty_responses(survey_path: Path) -> None:
    assert rank_llms_by_category_borda([], survey_path) == {}


def test_overall_ranking_pools_category_triplets(survey_path: Path) -> None:
    responses = [{"answers": {"ranking": {
        "q1": {"best": "model-a", "worst": "model-c"},
        "q2": {"best": "model-c", "worst": "model-a"},
        "q3": {"best": "model-a"},
    }}}]

    triplets = _module["extract_triplets_by_category"](
        responses, survey_path, skip_incomplete=True,
    )

    assert triplets == {
        "Accuracy": [("model-a", "model-b", "model-c")],
        "Clarity": [("model-c", "model-b", "model-a")],
    }
    assert _module["rank_overall"](triplets, _module["rank_borda"]) == [
        {"rank": 1, "model": "model-a", "score": 3.0, "answer_count": 2},
        {"rank": 2, "model": "model-b", "score": 3.0, "answer_count": 2},
        {"rank": 3, "model": "model-c", "score": 3.0, "answer_count": 2},
    ]
    assert [row["answer_count"] for row in _module["rank_overall"](
        triplets, _module["rank_plackett_luce"],
    )] == [2, 2, 2]
    assert _module["rank_overall"]({}, _module["rank_plackett_luce"]) == []


@pytest.fixture
def grouped_survey_path(tmp_path: Path) -> Path:
    path = tmp_path / "grouped-survey.json"
    path.write_text(json.dumps({
        "pages": [
            {
                "visibleIf": f"{{group}} = {group}",
                "elements": [
                    {
                        "type": "matrixdropdown",
                        "name": f"case{case}_group{group}_ranking",
                        "columns": [{"choices": [
                            {"value": model} for model in ("a", "b", "c")
                        ]}],
                        "rows": [
                            {"value": f"q{criterion}", "text": f"Criterion {criterion}"}
                            for criterion in range(6)
                        ],
                    },
                    {"type": "comment", "name": f"case{case}_group{group}_comment"},
                ],
            }
            for case in range(1, 28)
            for group in (1, 2)
        ],
    }), encoding="utf-8")
    return path


def test_limit_cases_caps_each_participant_and_rankings(
    grouped_survey_path: Path,
) -> None:
    responses = [
        {
            "label": f"p{participant:02d}",
            "token": f"token-{participant}",
            "status": "draft",
            "last_page": 27,
            "submitted_at": None,
            "answers": {
                f"case{case}_group{group}_ranking": {
                    f"q{criterion}": {"best": "a", "worst": "c"}
                    for criterion in range(6)
                }
                for case in reversed(range(1, 28))
            },
        }
        for participant, group in enumerate([1, 2] * 6, start=1)
    ]
    participants = [
        {"token": response["token"], "variables": {"group": group}}
        for response, group in zip(responses, [1, 2] * 6)
    ]

    limited = _module["limit_response_cases"](responses, grouped_survey_path, 10)
    summaries = _module["summarize_participants"](
        limited, participants, grouped_survey_path,
    )
    triplets = _module["extract_triplets_by_category"](limited, grouped_survey_path)

    assert len(limited) == len(responses) == 12
    assert all(row["completed_cases"] == 10 for row in summaries)
    assert all(row["incomplete_cases"] == 0 for row in summaries)
    assert all(row["complete_rankings"] == 60 for row in summaries)
    assert all(len(rankings) == 120 for rankings in triplets.values())
    assert all(len(response["answers"]) == 27 for response in responses)
    assert all(response["last_page"] == 27 for response in limited)


def test_limit_cases_uses_survey_order_not_answered_order(
    grouped_survey_path: Path,
) -> None:
    responses = [{"answers": {
        "case12_group2_comment": "Outside the limit",
        "case11_group2_ranking": {"q0": {"best": "a", "worst": "c"}},
        "case10_group2_ranking": {"q0": {"best": "a"}},
        "case10_group2_comment": "Inside the limit",
    }}]

    limited = _module["limit_response_cases"](responses, grouped_survey_path, 10)

    assert limited[0]["answers"] == {
        "case10_group2_ranking": {"q0": {"best": "a"}},
        "case10_group2_comment": "Inside the limit",
    }


@pytest.mark.parametrize("n_cases, expected_count", [(0, 0), (1, 1), (10, 1)])
def test_limit_cases_ungrouped_survey(
    survey_path: Path, n_cases: int, expected_count: int,
) -> None:
    limited = _module["limit_response_cases"](
        [{"answers": {"ranking": {"q1": {"best": "model-a", "worst": "model-c"}}}}],
        survey_path,
        n_cases,
    )

    assert len(limited) == 1
    assert len(limited[0]["answers"]) == expected_count


def test_limit_cases_rejects_negative_limit(survey_path: Path) -> None:
    with pytest.raises(ValueError, match="n_cases must be non-negative"):
        _module["limit_response_cases"]([], survey_path, -1)