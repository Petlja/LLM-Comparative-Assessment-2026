import json
from dataclasses import asdict
from functools import partial
from pathlib import Path
from runpy import run_path

import pytest


_module = run_path(
    str(Path(__file__).parents[1] / "suvrey-analisys" / "survey_responce.py")
)
rank_llms_by_category_borda = _module["rank_llms_by_category_borda"]
rank_llms_by_category_pl = _module["rank_llms_by_category_pl"]
RankingObservation = _module["RankingObservation"]
rank_observations = _module["rank_observations"]
rank_stratified_borda = _module["rank_stratified_borda"]


@pytest.fixture
def survey_path(tmp_path: Path) -> Path:
    path = tmp_path / "survey.json"
    path.write_text(json.dumps({
        "pages": [{"elements": [{
            "type": "matrixdropdown",
            "name": "TC-006__0__group-10__ranking",
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


@pytest.mark.parametrize("group", [1, 10])
def test_observations_extract_case_and_group(survey_path: Path, group: int) -> None:
    survey = json.loads(survey_path.read_text(encoding="utf-8"))
    question = f"TC-006__0__group-{group:02d}__ranking"
    survey["pages"][0]["elements"][0]["name"] = question
    survey_path.write_text(json.dumps(survey), encoding="utf-8")
    responses = [{"answers": {
        question: {"q1": {"best": "model-a", "worst": "model-c"}},
        "comment": "Ignored",
    }}]

    observations = _module["extract_observations_by_category"](responses, survey_path)

    assert list(observations) == ["Accuracy"]
    assert [asdict(observation) for observation in observations["Accuracy"]] == [{
        "case_key": "TC-006",
        "group": group,
        "category_id": "q1",
        "triplet": ("model-a", "model-b", "model-c"),
    }]


@pytest.mark.parametrize("question", [
    "ranking",
    "TC-006__0__ranking",
    "TC-006__0__group-ten__ranking",
    "TC-006__1__group-10__ranking",
    "TC-006__0__group-10__comment",
])
@pytest.mark.parametrize("skip_incomplete", [False, True])
def test_observations_reject_invalid_question_names(
    survey_path: Path, question: str, skip_incomplete: bool,
) -> None:
    survey = json.loads(survey_path.read_text(encoding="utf-8"))
    survey["pages"][0]["elements"][0]["name"] = question
    survey_path.write_text(json.dumps(survey), encoding="utf-8")
    responses = [{"answers": {
        question: {"q1": {"best": "model-a", "worst": "model-c"}},
    }}]

    with pytest.raises(ValueError, match="Invalid ranking question name"):
        _module["extract_observations_by_category"](
            responses, survey_path, skip_incomplete=skip_incomplete,
        )


def test_borda_averages_categories_and_ties(survey_path: Path) -> None:
    responses = [
        {"answers": {
            "comment": "Ignored",
            "TC-006__0__group-10__ranking": {
                "q1": {"best": "model-a", "worst": "model-c"},
                "q2": {"best": "model-c", "worst": "model-a"},
            },
        }},
        {"answers": {"TC-006__0__group-10__ranking": {
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
    responses = [{"answers": {"TC-006__0__group-10__ranking": {
        "q1": selection,
        "q2": {"best": "model-a", "worst": "model-c"},
    }}}]

    with pytest.raises(ValueError, match="Invalid ranking in TC-006__0__group-10__ranking, q1"):
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
        "name": "TC-007__0__group-10__ranking",
        "columns": [{"choices": [
            {"value": model} for model in ("model-a", "model-b", "model-d")
        ]}],
    }]})
    survey_path.write_text(json.dumps(survey), encoding="utf-8")
    responses = [
        {"answers": {"TC-006__0__group-10__ranking": {
            "q1": {"best": "model-a", "worst": "model-c"},
        }}},
        {"answers": {"TC-006__0__group-10__ranking": {
            "q1": {"best": "model-a", "worst": "model-c"},
        }}},
        {"answers": {"TC-007__0__group-10__ranking": {
            "q1": {"best": "model-d", "worst": "model-a"},
        }}},
        {"answers": {"TC-006__0__group-10__ranking": {"q1": {"best": "model-a"}}}},
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
        "name": "TC-007__0__group-10__ranking",
        "columns": [{"choices": [
            {"value": model} for model in ("model-a", "model-b", "model-d")
        ]}],
    }]})
    survey_path.write_text(json.dumps(survey), encoding="utf-8")
    responses = [{"answers": {
        "TC-006__0__group-10__ranking": {
            "q1": {"best": "model-a", "worst": "model-c"},
            "q2": {"best": "model-c", "worst": "model-a"},
        },
        "TC-007__0__group-10__ranking": {
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


@pytest.mark.parametrize("rank_method", [_module["rank_borda"], _module["rank_plackett_luce"]])
def test_rankings_split_by_inclusive_flag(survey_path: Path, tmp_path: Path, rank_method) -> None:
    survey = json.loads(survey_path.read_text(encoding="utf-8"))
    matrix = survey["pages"][0]["elements"][0]
    survey["pages"] = [
        {"elements": [{**matrix, "name": f"{case}__0__group-01__ranking"}]}
        for case in ("TC-001", "TC-002", "TC-003")
    ]
    survey_path.write_text(json.dumps(survey), encoding="utf-8")
    cases_path = tmp_path / "cases.yml"
    cases_path.write_text(
        "- case_key: TC-001\n  inclusive: true\n"
        "- case_key: TC-002\n  inclusive: false\n"
        "- case_key: TC-003\n",
        encoding="utf-8",
    )
    responses = [{"answers": {
        "TC-001__0__group-01__ranking": {
            "q1": {"best": "model-a", "worst": "model-c"},
            "q2": {"best": "model-a"},
        },
        "TC-002__0__group-01__ranking": {
            "q1": {"best": "model-c", "worst": "model-a"},
        },
        "TC-003__0__group-01__ranking": {
            "q1": {"best": "model-c", "worst": "model-a"},
        },
        "comment": "ignored",
    }}]

    split = _module["extract_triplets_by_case_type"](
        responses, survey_path, cases_path, skip_incomplete=True,
    )

    assert list(split) == ["inclusive", "general", "total"]
    assert [len(split[kind]["Accuracy"]) for kind in split] == [1, 2, 3]
    assert all("Clarity" not in categories for categories in split.values())
    assert rank_method(split["inclusive"]["Accuracy"])[0]["model"] == "model-a"
    assert rank_method(split["general"]["Accuracy"])[0]["model"] == "model-c"
    assert _module["rank_overall"](split["total"], rank_method)[0]["answer_count"] == 3
    assert responses[0]["answers"]["TC-001__0__group-01__ranking"]["q2"] == {"best": "model-a"}
    assert _module["extract_triplets_by_case_type"]([], survey_path, cases_path) == {
        "inclusive": {}, "general": {}, "total": {},
    }
    cases_path.write_text("- case_key: TC-001\n  inclusive: true\n", encoding="utf-8")
    with pytest.raises(ValueError, match="No case definition"):
        _module["extract_triplets_by_case_type"]([], survey_path, cases_path)


def test_borda_empty_responses(survey_path: Path) -> None:
    assert rank_llms_by_category_borda([], survey_path) == {}


def test_overall_ranking_pools_category_triplets(survey_path: Path) -> None:
    responses = [{"answers": {"TC-006__0__group-10__ranking": {
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
                        "name": f"TC-{case:03d}__0__group-{group:02d}__ranking",
                        "columns": [{"choices": [
                            {"value": model} for model in ("a", "b", "c")
                        ]}],
                        "rows": [
                            {"value": f"q{criterion}", "text": f"Criterion {criterion}"}
                            for criterion in range(6)
                        ],
                    },
                    {"type": "comment", "name": f"TC-{case:03d}__0__group-{group:02d}__comment"},
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
                f"TC-{case:03d}__0__group-{group:02d}__ranking": {
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
        "TC-012__0__group-02__comment": "Outside the limit",
        "TC-011__0__group-02__ranking": {"q0": {"best": "a", "worst": "c"}},
        "TC-010__0__group-02__ranking": {"q0": {"best": "a"}},
        "TC-010__0__group-02__comment": "Inside the limit",
    }}]

    limited = _module["limit_response_cases"](responses, grouped_survey_path, 10)

    assert limited[0]["answers"] == {
        "TC-010__0__group-02__ranking": {"q0": {"best": "a"}},
        "TC-010__0__group-02__comment": "Inside the limit",
    }


@pytest.mark.parametrize("min_cases, max_cases", [(2, 5), (5, 5), (25, 99)])
def test_limit_cases_inclusive_range_per_group(
    grouped_survey_path: Path, min_cases: int, max_cases: int,
) -> None:
    responses = [{"answers": {
        f"TC-{case:03d}__0__group-{group:02d}__{kind}": "answer"
        for case in reversed(range(1, 28))
        for kind in ("ranking", "comment")
    }} for group in (1, 2)]

    limited = _module["limit_response_cases"](
        responses, grouped_survey_path, max_cases, min_cases=min_cases,
    )

    for group, response in enumerate(limited, start=1):
        assert set(response["answers"]) == {
            f"TC-{case:03d}__0__group-{group:02d}__{kind}"
            for case in range(min_cases, min(max_cases, 27) + 1)
            for kind in ("ranking", "comment")
        }
    assert all(len(response["answers"]) == 54 for response in responses)


@pytest.mark.parametrize("min_cases, max_cases, message", [
    (0, 5, "min_cases must be at least 1"),
    (-1, 5, "min_cases must be at least 1"),
    (6, 5, "min_cases must not exceed n_cases"),
])
def test_limit_cases_rejects_invalid_range(
    survey_path: Path, min_cases: int, max_cases: int, message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _module["limit_response_cases"](
            [], survey_path, max_cases, min_cases=min_cases,
        )


@pytest.mark.parametrize("n_cases, expected_count", [(0, 0), (1, 1), (10, 1)])
def test_limit_cases_ungrouped_survey(
    survey_path: Path, n_cases: int, expected_count: int,
) -> None:
    limited = _module["limit_response_cases"](
        [{"answers": {"TC-006__0__group-10__ranking": {
            "q1": {"best": "model-a", "worst": "model-c"},
        }}}],
        survey_path,
        n_cases,
    )

    assert len(limited) == 1
    assert len(limited[0]["answers"]) == expected_count


def test_limit_cases_rejects_negative_limit(survey_path: Path) -> None:
    with pytest.raises(ValueError, match="n_cases must be non-negative"):
        _module["limit_response_cases"]([], survey_path, -1)


@pytest.fixture
def stratified_responses(survey_path: Path, tmp_path: Path):
    survey = json.loads(survey_path.read_text(encoding="utf-8"))
    matrix = survey["pages"][0]["elements"][0]
    questions = [
        "TC-001__0__group-01__ranking",
        "TC-001__0__group-02__ranking",
        "TC-002__0__group-01__ranking",
        "TC-003__0__group-01__ranking",
    ]
    survey["pages"] = [
        {"elements": [{
            **matrix,
            "name": question,
            "columns": [{"choices": [
                {"value": model}
                for model in ("model-a", "model-b", "model-d" if index == 1 else "model-c")
            ]}],
        }]}
        for index, question in enumerate(questions)
    ]
    survey_path.write_text(json.dumps(survey), encoding="utf-8")
    (tmp_path / "cases.yml").write_text(
        "- case_key: TC-001\n  inclusive: true\n"
        "- case_key: TC-002\n"
        "- case_key: TC-003\n",
        encoding="utf-8",
    )
    return [
        {"answers": {questions[question]: {
            category: {"best": best, "worst": worst},
        }}}
        for question, category, best, worst, count in [
            (0, "q1", "model-a", "model-c", 20),
            (1, "q1", "model-b", "model-a", 2),
            (0, "q2", "model-a", "model-c", 1),
            (2, "q2", "model-c", "model-a", 3),
        ]
        for _ in range(count)
    ]


def test_stratified_borda_equal_case_weight_and_model_coverage(
    survey_path: Path, stratified_responses,
) -> None:
    results = _module["rank_llms_by_category_stratified_borda"](
        stratified_responses, survey_path,
    )

    assert results == {
        "Accuracy": [
            {"rank": 1, "model": "model-a", "score": pytest.approx(102 / 22), "answer_count": 22, "stratum_count": 1},
            {"rank": 2, "model": "model-b", "score": pytest.approx(70 / 22), "answer_count": 22, "stratum_count": 1},
            {"rank": 3, "model": "model-d", "score": 3.0, "answer_count": 2, "stratum_count": 1},
            {"rank": 4, "model": "model-c", "score": 1.0, "answer_count": 20, "stratum_count": 1},
        ],
        "Clarity": [
            {"rank": 1, "model": "model-a", "score": 3.0, "answer_count": 4, "stratum_count": 2},
            {"rank": 2, "model": "model-b", "score": 3.0, "answer_count": 4, "stratum_count": 2},
            {"rank": 3, "model": "model-c", "score": 3.0, "answer_count": 4, "stratum_count": 2},
        ],
    }
    ordinary = rank_llms_by_category_borda(stratified_responses, survey_path)
    assert [
        {key: value for key, value in row.items() if key != "stratum_count"}
        for row in results["Accuracy"]
    ] == ordinary["Accuracy"]
    assert ordinary["Clarity"][0]["model"] == "model-c"
    assert ordinary["Clarity"][0]["score"] == 4


def test_stratum_preserves_case() -> None:
    first = RankingObservation("TC-001", 1, "q1", ("a", "b", "c"))
    second = RankingObservation("TC-002", 1, "q1", ("c", "b", "a"))

    results = rank_stratified_borda([first] * 20 + [second] * 2)

    assert all(row["score"] == 3 for row in results)
    assert all(row["answer_count"] == 22 for row in results)
    assert all(row["stratum_count"] == 2 for row in results)


@pytest.mark.parametrize("group, category", [(2, "q1"), (1, "q2"), (2, "q2")])
def test_stratum_pools_groups_and_categories_by_answer_count(group, category) -> None:
    first = RankingObservation("TC-001", 1, "q1", ("a", "b", "c"))
    second = RankingObservation("TC-001", group, category, ("c", "b", "a"))

    results = rank_stratified_borda([first] * 20 + [second] * 2)

    assert results == [
        {"rank": 1, "model": "a", "score": pytest.approx(102 / 22), "answer_count": 22, "stratum_count": 1},
        {"rank": 2, "model": "b", "score": 3, "answer_count": 22, "stratum_count": 1},
        {"rank": 3, "model": "c", "score": pytest.approx(30 / 22), "answer_count": 22, "stratum_count": 1},
    ]


def test_stratified_borda_averages_within_strata_and_is_replication_invariant() -> None:
    first = [
        RankingObservation("TC-001", 1, "q1", ("a", "b", "c")),
        RankingObservation("TC-001", 1, "q1", ("b", "a", "c")),
    ]
    second = [RankingObservation("TC-002", 1, "q1", ("c", "b", "a"))]

    original = rank_stratified_borda(first + second)
    replicated = rank_stratified_borda(first * 7 + second)

    assert {row["model"]: row["score"] for row in original} == {"b": 3.5, "c": 3, "a": 2.5}
    assert [
        {key: value for key, value in row.items() if key != "answer_count"}
        for row in original
    ] == [
        {key: value for key, value in row.items() if key != "answer_count"}
        for row in replicated
    ]
    assert all(row["answer_count"] == 15 for row in replicated)


def test_stratified_borda_matches_borda_with_equal_stratum_sizes() -> None:
    observations = [
        RankingObservation("TC-001", 1, "q1", ("a", "b", "c")),
        RankingObservation("TC-001", 1, "q1", ("b", "a", "c")),
        RankingObservation("TC-002", 1, "q1", ("c", "b", "a")),
        RankingObservation("TC-002", 1, "q1", ("a", "b", "c")),
    ]

    assert [
        {key: value for key, value in row.items() if key != "stratum_count"}
        for row in rank_stratified_borda(observations)
    ] == rank_observations(observations, "borda")


@pytest.mark.parametrize("selection", [
    {}, {"best": "model-a"}, {"worst": "model-c"},
    {"best": "model-a", "worst": "model-a"},
    {"best": "unknown", "worst": "model-c"},
])
def test_stratified_borda_preserves_incomplete_ranking_policy(
    survey_path: Path, selection,
) -> None:
    responses = [{"answers": {"TC-006__0__group-10__ranking": {
        "q1": selection, "q2": {"best": "model-a", "worst": "model-c"},
    }}}]
    rank = _module["rank_llms_by_category_stratified_borda"]
    with pytest.raises(ValueError, match="Invalid ranking in TC-006__0__group-10__ranking, q1"):
        rank(responses, survey_path)
    results = rank(responses, survey_path, skip_incomplete=True)
    assert list(results) == ["Clarity"]
    assert all(row["stratum_count"] == row["answer_count"] == 1 for row in results["Clarity"])
    assert responses[0]["answers"]["TC-006__0__group-10__ranking"]["q1"] == selection


@pytest.mark.parametrize("method", ["borda", "plackett_luce", "stratified_borda"])
def test_observation_pipeline_by_category_case_type_and_overall(
    survey_path: Path, tmp_path: Path, stratified_responses, method,
) -> None:
    cases_path = tmp_path / "cases.yml"
    observations = _module["extract_observations_by_case_type"](
        stratified_responses, survey_path, cases_path,
    )
    triplets = _module["extract_triplets_by_case_type"](
        stratified_responses, survey_path, cases_path,
    )
    assert list(observations) == ["inclusive", "general", "total"]
    assert [len(items) for items in observations["total"].values()] == [22, 4]
    assert observations["total"]["Accuracy"][0] == RankingObservation(
        "TC-001", 1, "q1", ("model-a", "model-b", "model-c"),
    )
    rank = partial(rank_observations, method=method)
    for case_type, categories in observations.items():
        assert {
            category: [observation.triplet for observation in items]
            for category, items in categories.items()
        } == triplets[case_type]
        by_category = _module["rank_by_category"](categories, rank)
        overall = _module["rank_overall"](categories, rank)
        if method != "stratified_borda":
            legacy_rank = _module[f"rank_{method}"]
            assert by_category == _module["rank_by_category"](triplets[case_type], legacy_rank)
            assert overall == _module["rank_overall"](triplets[case_type], legacy_rank)
        elif case_type == "total":
            assert {row["model"]: row["score"] for row in overall} == {
                "model-a": pytest.approx(65 / 23), "model-b": pytest.approx(71 / 23),
                "model-c": 3, "model-d": 3,
            }
            assert {row["model"]: row["stratum_count"] for row in overall} == {
                "model-a": 2, "model-b": 2, "model-c": 2, "model-d": 1,
            }
        elif case_type == "general":
            assert overall[0]["model"] == "model-c"
            assert all(row["stratum_count"] == 1 for row in overall)
        else:
            assert {row["model"]: row["score"] for row in overall} == {
                "model-a": pytest.approx(107 / 23), "model-b": pytest.approx(73 / 23),
                "model-c": 1, "model-d": 3,
            }
            assert all(row["stratum_count"] == 1 for row in overall)


def test_stratified_borda_empty_and_unknown_method(survey_path: Path) -> None:
    assert rank_stratified_borda([]) == []
    for method in ("borda", "plackett_luce", "stratified_borda"):
        assert rank_observations([], method) == []
        assert _module["rank_overall"]({}, partial(rank_observations, method=method)) == []
    assert _module["rank_llms_by_category_stratified_borda"]([], survey_path) == {}
    with pytest.raises(ValueError, match="Unknown ranking method"):
        rank_observations([], "not-a-method")


def test_stratified_borda_respects_case_limit(grouped_survey_path: Path) -> None:
    responses = [{"answers": {
        f"TC-{case:03d}__0__group-{group:02d}__ranking": {"q0": {"best": "a", "worst": "c"}}
        for case in range(1, 28)
        for group in (1, 2)
    }}] * 3
    limited = _module["limit_response_cases"](responses, grouped_survey_path, 10)
    results = _module["rank_llms_by_category_stratified_borda"](limited, grouped_survey_path)
    assert all(row["stratum_count"] == 10 for row in results["Criterion 0"])
    assert all(row["answer_count"] == 60 for row in results["Criterion 0"])


@pytest.mark.parametrize("method", ["borda", "plackett_luce", "stratified_borda"])
@pytest.mark.parametrize("empty", [False, True])
def test_live_notebook_rankings_and_head_to_head(
    survey_path: Path, tmp_path: Path, stratified_responses, monkeypatch, method, empty,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    analysis_dir = Path(__file__).parents[1] / "suvrey-analisys"
    monkeypatch.syspath_prepend(str(analysis_dir))
    notebook = json.loads((analysis_dir / "live-analisys.ipynb").read_text(encoding="utf-8"))
    sources = [
        "".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "code"
    ]
    for source in sources:
        compile(source, "live-analisys.ipynb", "exec")

    working_dir = tmp_path / "analysis"
    working_dir.mkdir()
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    (eval_dir / "test-cases.yml").write_text(
        (tmp_path / "cases.yml").read_text(encoding="utf-8"), encoding="utf-8",
    )
    monkeypatch.chdir(working_dir)
    namespace = {}
    exec(sources[0], namespace)
    namespace.update({
        "responses": [] if empty else stratified_responses,
        "survey_path": survey_path,
        "display": lambda *args: None,
    })
    ranking_source = next(source for source in sources if "observations_by_case_type =" in source)
    assert ranking_source.count('ranking_method = "borda"') == 1
    exec(ranking_source.replace('ranking_method = "borda"', f'ranking_method = "{method}"'), namespace)

    dataset = namespace["overall_rankings"].set_index("model")
    if empty:
        assert dataset.empty
        assert namespace["rankings_by_category"] == {}
    else:
        assert dataset.loc["model-a", "answer_count_total"] == 26
        assert dataset.loc["model-d", "answer_count_general"] == 0
        if method == "stratified_borda":
            assert dataset.loc["model-a", "score_total"] == pytest.approx(65 / 23)
            assert dataset.loc["model-a", "stratum_count_total"] == 2
            assert dataset.loc["model-d", "stratum_count_general"] == 0
            assert str(dataset["stratum_count_total"].dtype) == "Int64"
        else:
            assert "stratum_count_total" not in dataset
            if method == "borda":
                assert dataset.loc["model-a", "score_total"] == pytest.approx(110 / 26)

    head_to_head_source = next(source for source in sources if "comparison_models =" in source)
    exec(head_to_head_source.replace(
        'comparison_models = ("Qwen/Qwen3-14B", "Qwen/Qwen3-32B")',
        'comparison_models = ("model-a", "model-b")',
    ), namespace)
    assert namespace["overall_head_to_head"]["wins_total"].to_dict() == {
        "model-a": 0 if empty else 21, "model-b": 0 if empty else 5,
    }