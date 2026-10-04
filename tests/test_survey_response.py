import json
from pathlib import Path
from runpy import run_path

import pytest


rank_llms_by_category_borda = run_path(
    str(Path(__file__).parents[1] / "suvrey-analisys" / "survey_responce.py")
)["rank_llms_by_category_borda"]


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
            {"rank": 1, "model": "model-a", "score": 4.0},
            {"rank": 2, "model": "model-b", "score": 4.0},
            {"rank": 3, "model": "model-c", "score": 1.0},
        ],
        "Clarity": [
            {"rank": 1, "model": "model-c", "score": 5},
            {"rank": 2, "model": "model-b", "score": 3},
            {"rank": 3, "model": "model-a", "score": 1},
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
        {"rank": 1, "model": "model-a", "score": 5},
        {"rank": 2, "model": "model-b", "score": 3},
        {"rank": 3, "model": "model-c", "score": 1},
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
        {"rank": 1, "model": "model-d", "score": 5.0},
        {"rank": 2, "model": "model-a", "score": pytest.approx(11 / 3)},
        {"rank": 3, "model": "model-b", "score": 3.0},
        {"rank": 4, "model": "model-c", "score": 1.0},
    ]}


def test_borda_empty_responses(survey_path: Path) -> None:
    assert rank_llms_by_category_borda([], survey_path) == {}