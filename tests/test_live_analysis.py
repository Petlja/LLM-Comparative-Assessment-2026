import json
import re
from datetime import datetime
from io import StringIO
from pathlib import Path
from runpy import run_path
from urllib.request import Request

import pandas as pd
import pytest


@pytest.mark.parametrize("min_completed_cases", [-1, 0, 2, 3, 4])
@pytest.mark.parametrize("initial_responses", [
    [],
    [{"label": "p01", "answers": {"q1": "Odgovor čćš"}},
     {"label": "test01", "answers": {"q1": "synthetic"}}],
])
def test_fetch_saves_raw_responses_and_overwrites_same_minute(
    tmp_path: Path, monkeypatch, initial_responses: list[dict],
    min_completed_cases: int,
) -> None:
    notebook_path = Path(__file__).parents[1] / "suvrey-analisys" / "live-analisys.ipynb"
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    source = "".join(notebook["cells"][2]["source"])
    source = re.sub(
        r"(?m)^min_completed_cases = .*",
        f"min_completed_cases = {min_completed_cases}",
        source,
    )
    analysis_dir = tmp_path / "suvrey-analisys"
    analysis_dir.mkdir()
    (analysis_dir / "live-analisys-config.json").write_text(
        json.dumps({"base_url": "http://localhost", "admin_token": "test-token"}),
        encoding="utf-8",
    )
    monkeypatch.chdir(analysis_dir)
    raw_responses = initial_responses
    participants = [{"label": "p01"}]
    calls = []
    limited_responses = []
    completed_cases = {"p01": 2, "p02": 3}
    summarized_responses = []

    class FixedDatetime:
        @staticmethod
        def now() -> datetime:
            return datetime(2026, 10, 9, 13, 3)

    helper_namespace = run_path(
        str(Path(__file__).parents[1] / "suvrey-analisys" / "survey_responce.py")
    )
    prepare_live_responses = helper_namespace["prepare_live_responses"]
    helper_globals = prepare_live_responses.__globals__

    def urlopen(request: Request, timeout: int) -> StringIO:
        assert timeout == 30
        calls.append(request.full_url)
        data = participants if request.full_url.endswith("/api/participants/") else raw_responses
        return StringIO(json.dumps(data))

    def limit_response_cases(responses, survey_path, n_cases, *, min_cases):
        assert min_cases == 1
        assert n_cases == 99
        limited_responses.append(responses)
        return []

    def summarize_participants(responses, participant_data, survey_path):
        assert participant_data == participants
        assert responses == [
            response for response in raw_responses
            if response["label"].startswith("p")
        ]
        assert len(summarized_responses) == len(limited_responses)
        summarized_responses.append(responses)
        return [
            {"completed_cases": completed_cases[response["label"]]}
            for response in responses
        ]

    monkeypatch.setitem(helper_globals, "datetime", FixedDatetime)
    monkeypatch.setitem(helper_globals, "urlopen", urlopen)
    monkeypatch.setitem(helper_globals, "limit_response_cases", limit_response_cases)
    monkeypatch.setitem(helper_globals, "summarize_participants", summarize_participants)
    monkeypatch.setitem(helper_globals, "CONFIG_PATH", analysis_dir / "live-analisys-config.json")
    monkeypatch.setitem(helper_globals, "SURVEY_PATH", "../eval/output/survey.json")
    monkeypatch.setitem(helper_globals, "CASES_PATH", "../eval/test-cases.yml")
    monkeypatch.setitem(helper_globals, "RESPONSE_DIR", Path("..") / "eval" / "final-assesment")

    namespace = {
        "prepare_live_responses": prepare_live_responses,
    }
    if min_completed_cases < 0:
        with pytest.raises(ValueError, match="min_completed_cases must be non-negative"):
            exec(compile(source, "live-analisys.ipynb:fetch", "exec"), namespace)
        assert calls == []
        return

    for data in [initial_responses, [{"label": "p02", "answers": {"q2": "updated"}}]]:
        raw_responses = data
        exec(compile(source, "live-analisys.ipynb:fetch", "exec"), namespace)
        output_dir = tmp_path / "eval" / "final-assesment"
        snapshots = list(output_dir.iterdir())
        assert len(snapshots) == 1
        assert snapshots[0].name == "responce-26-10-09-13-03.json"
        assert json.loads(snapshots[0].read_text(encoding="utf-8")) == data
        assert namespace["responses"] == []
        assert namespace["participants"] == participants
        assert limited_responses[-1] == [
            response for response in data if response["label"].startswith("p")
            and completed_cases[response["label"]] >= min_completed_cases
        ]
    assert calls == ["http://localhost/api/responses", "http://localhost/api/participants/"] * 2
    assert len(summarized_responses) == (2 if min_completed_cases > 0 else 0)


def test_prepare_live_responses_filters_answers_by_course(
    tmp_path: Path, monkeypatch,
) -> None:
    helper_namespace = run_path(
        str(Path(__file__).parents[1] / "suvrey-analisys" / "survey_responce.py")
    )
    prepare_live_responses = helper_namespace["prepare_live_responses"]
    monkeypatch.setitem(
        prepare_live_responses.__globals__,
        "limit_response_cases",
        lambda responses, survey_path, n_cases, *, min_cases: responses,
    )
    cases_path = tmp_path / "test-cases.yml"
    cases_path.write_text(
        "- case_key: TC-001\n  course_key: course-a\n"
        "- case_key: TC-002\n  course_key: course-b\n",
        encoding="utf-8",
    )
    raw_responses = [{
        "label": "p01",
        "answers": {
            "TC-001__0__group-01__ranking": {"q1": "a"},
            "TC-002__0__group-01__ranking": {"q1": "b"},
        },
    }]

    def fetch_api(path: str) -> list[dict]:
        return raw_responses if path == "/api/responses" else []

    monkeypatch.setitem(prepare_live_responses.__globals__, "fetch_api", fetch_api)
    responses, _ = prepare_live_responses(
        "survey.json", cases_path, tmp_path / "snapshots",
        n_cases_min=1, n_cases_max=99, min_completed_cases=0,
        course_keys=["course-a"],
    )

    assert responses == [{
        "label": "p01",
        "answers": {"TC-001__0__group-01__ranking": {"q1": "a"}},
    }]


@pytest.mark.parametrize("course_keys", [None, []])
def test_prepare_live_responses_empty_course_filter_keeps_all_answers(
    tmp_path: Path, monkeypatch, course_keys: list[str] | None,
) -> None:
    helper_namespace = run_path(
        str(Path(__file__).parents[1] / "suvrey-analisys" / "survey_responce.py")
    )
    prepare_live_responses = helper_namespace["prepare_live_responses"]
    monkeypatch.setitem(
        prepare_live_responses.__globals__,
        "limit_response_cases",
        lambda responses, survey_path, n_cases, *, min_cases: responses,
    )
    raw_responses = [{
        "label": "p01",
        "answers": {"TC-001__0__group-01__ranking": {"q1": "a"}},
    }]

    def fetch_api(path: str) -> list[dict]:
        return raw_responses if path == "/api/responses" else []

    monkeypatch.setitem(prepare_live_responses.__globals__, "fetch_api", fetch_api)
    responses, _ = prepare_live_responses(
        "survey.json", tmp_path / "missing.yml",
        tmp_path / "snapshots", n_cases_min=1, n_cases_max=99,
        min_completed_cases=0, course_keys=course_keys,
    )

    assert responses == raw_responses


@pytest.fixture
def timeline_cell() -> str:
    notebook_path = (
        Path(__file__).parents[1] / "suvrey-analisys" / "live-analisys.ipynb"
    )
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    cell = next(
        cell for cell in notebook["cells"]
        if cell["cell_type"] == "code"
        and "".join(cell["source"]).startswith("timeline_participant =")
    )
    assert cell["cell_type"] == "code"
    return "".join(cell["source"])


def run_timeline(cell: str, questions: list[dict], participants: list[dict]) -> dict:
    calls = []
    displayed = []

    def fetch_api(path: str) -> list[dict]:
        calls.append(path)
        return questions

    namespace = {
        "pd": pd,
        "participants": participants,
        "fetch_api": fetch_api,
        "Markdown": str,
        "display": displayed.append,
    }
    exec(compile(cell, "live-analisys.ipynb:timeline", "exec"), namespace)
    assert calls == ["/api/participant-questions"]
    namespace["displayed"] = displayed
    return namespace


def test_timeline_filters_participant_and_sorts_timestamps(timeline_cell: str) -> None:
    participants = [
        {"token": "selected", "label": "p20"},
        {"token": "excluded", "label": "p21"},
    ]
    questions = [
        {"token": "selected", "question_name": "later", "first_answered_at": "2026-10-06T12:00:00"},
        {"token": "excluded", "question_name": "other", "first_answered_at": "2026-10-06T09:00:00"},
        {"token": "selected", "question_name": "earlier", "first_answered_at": "2026-10-06T10:00:00.123000"},
        {"token": "selected", "question_name": "same_time", "first_answered_at": "2026-10-06T10:00:00.123000"},
    ]

    namespace = run_timeline(timeline_cell, questions, participants)
    timeline = namespace["question_timeline"]

    assert namespace["timeline_participant"] == "p20"
    assert list(timeline.columns) == ["question_name", "first_answered_at"]
    assert timeline["question_name"].tolist() == ["earlier", "same_time", "later"]
    assert str(timeline["first_answered_at"].dt.tz) == "UTC"
    assert isinstance(namespace["displayed"][-1], pd.DataFrame)
    assert namespace["displayed"][-1]["first_answered_at"].tolist() == [
        "2026-10-06 12:00",
        "2026-10-06 12:00",
        "2026-10-06 14:00",
    ]


def test_timeline_reports_no_records(timeline_cell: str) -> None:
    namespace = run_timeline(
        timeline_cell, [], [{"token": "selected", "label": "p20"}],
    )

    assert namespace["question_timeline"].empty
    assert namespace["displayed"][-1] == "No question timestamps recorded for this participant."


@pytest.mark.parametrize("participants", [
    [],
    [{"token": "a", "label": "p20"}, {"token": "b", "label": "p20"}],
])
def test_timeline_rejects_missing_or_ambiguous_participant(
    timeline_cell: str, participants: list[dict],
) -> None:
    with pytest.raises(ValueError, match="Expected one participant labelled 'p20'"):
        run_timeline(timeline_cell, [], participants)


def test_timeline_rejects_invalid_timestamp(timeline_cell: str) -> None:
    with pytest.raises(ValueError):
        run_timeline(
            timeline_cell,
            [{"token": "selected", "question_name": "ranking", "first_answered_at": "invalid"}],
            [{"token": "selected", "label": "p07"}],
        )


def test_extract_observations_uses_shared_paths_by_default(tmp_path: Path) -> None:
    helper_namespace = run_path(
        str(Path(__file__).parents[1] / "suvrey-analisys" / "survey_responce.py")
    )
    extract_observations = helper_namespace["extract_observations_by_case_type"]
    helper_globals = extract_observations.__globals__
    survey_path = tmp_path / "survey.json"
    survey_path.write_text(json.dumps({"pages": [{"elements": [{
        "type": "matrixdropdown",
        "name": "TC-001__0__group-01__ranking",
        "columns": [{"choices": [{"value": model} for model in ("a", "b", "c")]}],
        "rows": [{"value": "q1", "text": "Accuracy"}],
    }]}]}), encoding="utf-8")
    cases_path = tmp_path / "test-cases.yml"
    cases_path.write_text("- case_key: TC-001\n  inclusive: true\n", encoding="utf-8")
    helper_globals["SURVEY_PATH"] = survey_path
    helper_globals["CASES_PATH"] = cases_path
    responses = [{"answers": {
        "TC-001__0__group-01__ranking": {
            "q1": {"best": "a", "worst": "c"},
        },
    }}]

    observations = extract_observations(responses, skip_incomplete=True)

    assert observations["total"]["Accuracy"][0].triplet == ("a", "b", "c")
    assert observations["inclusive"]["Accuracy"][0].case_key == "TC-001"
    assert observations["general"] == {}


@pytest.mark.parametrize("rank_method", ["rank_borda", "rank_plackett_luce"])
@pytest.mark.parametrize("case_keys", [[], ["TC-001"], ["TC-004"], ["TC-001", "TC-004"]])
def test_ranking_datasets_include_case_type_columns(
    tmp_path: Path, monkeypatch, rank_method: str, case_keys: list[str],
) -> None:
    analysis_dir = Path(__file__).parents[1] / "suvrey-analisys"
    monkeypatch.syspath_prepend(str(analysis_dir))
    monkeypatch.chdir(analysis_dir)
    import survey_responce

    notebook = json.loads((analysis_dir / "live-analisys.ipynb").read_text(encoding="utf-8"))
    source = "".join(notebook["cells"][6]["source"])
    source = source.replace("rank_method = rank_borda", f"rank_method = {rank_method}")
    survey_path = tmp_path / "survey.json"
    survey_path.write_text(json.dumps({"pages": [
        {"elements": [{
            "type": "matrixdropdown",
            "name": f"{case_key}__0__group-01__ranking",
            "columns": [{"choices": [{"value": model} for model in models]}],
            "rows": [{"value": "q1", "text": "Accuracy"}],
        }]}
        for case_key, models in [
            ("TC-001", ["a", "b", "c"]),
            ("TC-004", ["d", "b", "a"]),
        ]
    ]}), encoding="utf-8")
    responses = [{"answers": {
        f"{case_key}__0__group-01__ranking": {
            "q1": {"best": "a" if case_key == "TC-001" else "d", "worst": "c" if case_key == "TC-001" else "a"},
        }
        for case_key in case_keys
    }}]
    displayed = []
    namespace = {
        "pd": pd, "responses": responses, "survey_path": survey_path,
        "CASES_PATH": survey_responce.CASES_PATH,
        "rank_borda": survey_responce.rank_borda,
        "rank_plackett_luce": survey_responce.rank_plackett_luce,
        "rank_by_category": survey_responce.rank_by_category,
        "rank_overall": survey_responce.rank_overall,
        "Markdown": str, "display": displayed.append,
    }
    exec(compile(source, "live-analisys.ipynb:rankings", "exec"), namespace)

    comparison_source = (
        'comparison_models = ("a", "b")\n'
        + "".join(notebook["cells"][-1]["source"]).split("\n", 1)[1]
    )
    comparison_namespace = {**namespace, "display": lambda output: None}
    exec(compile(comparison_source, "live-analisys.ipynb:head-to-head", "exec"), comparison_namespace)
    assert comparison_namespace["overall_head_to_head"].to_dict("list") == {
        "wins_total": [int("TC-001" in case_keys), int("TC-004" in case_keys)],
        "wins_inclusive": [int("TC-001" in case_keys), 0],
        "wins_general": [0, int("TC-004" in case_keys)],
    }

    overall = namespace["overall_rankings"]
    assert overall.index.name == "rank_total"
    assert list(overall.columns) == [
        "model", "score_total", "answer_count_total",
        "rank_inclusive", "score_inclusive", "answer_count_inclusive",
        "rank_general", "score_general", "answer_count_general",
    ]
    if not case_keys:
        assert overall.empty
        assert namespace["rankings_by_category"] == {}
        assert displayed[-1] == "No complete rankings yet."
        return
    rendered_tables = [output.data for output in displayed if hasattr(output, "data")]
    assert len(rendered_tables) == 2
    for html in rendered_tables:
        assert html.count("<table ") == 3
        assert html.index("<h4>Total</h4>") < html.index("<h4>Inclusive</h4>") < html.index("<h4>General</h4>")
        assert "display: flex" in html
        assert "overflow-x: auto" in html
        assert "&lt;NA&gt;" not in html
        assert "rank_total" not in html
        assert "score_inclusive" not in html
    for dataset in (overall, namespace["rankings_by_category"]["Accuracy"]):
        assert dataset["answer_count_total"].equals(
            dataset["answer_count_inclusive"] + dataset["answer_count_general"]
        )
        for kind, case_key, winner in [("inclusive", "TC-001", "a"), ("general", "TC-004", "d")]:
            if case_key in case_keys:
                assert dataset.loc[dataset[f"rank_{kind}"] == 1, "model"].tolist() == [winner]
            else:
                assert dataset[f"rank_{kind}"].isna().all()
                assert dataset[f"score_{kind}"].isna().all()
                assert (dataset[f"answer_count_{kind}"] == 0).all()


@pytest.fixture
def head_to_head_cell() -> str:
    notebook_path = Path(__file__).parents[1] / "suvrey-analisys" / "live-analisys.ipynb"
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    return (
        'comparison_models = ("Qwen/Qwen3-14B", "Qwen/Qwen3-32B")\n'
        + "".join(notebook["cells"][-1]["source"]).split("\n", 1)[1]
    )


def run_head_to_head(cell: str, inclusive: dict, general: dict) -> dict:
    import matplotlib

    matplotlib.use("Agg")

    categories = dict.fromkeys([*inclusive, *general])
    total = {
        category: inclusive.get(category, []) + general.get(category, [])
        for category in categories
    }
    displayed = []
    namespace = {
        "pd": pd, "Markdown": str, "display": displayed.append,
        "triplets_by_case_type": {
            "total": total, "inclusive": inclusive, "general": general,
        },
    }
    exec(compile(cell, "live-analisys.ipynb:head-to-head", "exec"), namespace)
    namespace["displayed"] = displayed
    return namespace


def test_head_to_head_counts_relative_order_and_excludes_indirect_comparisons(
    head_to_head_cell: str,
) -> None:
    from itertools import permutations

    model_a, model_b = "Qwen/Qwen3-14B", "Qwen/Qwen3-32B"
    direct = list(permutations([model_a, model_b, "other"]))
    namespace = run_head_to_head(
        head_to_head_cell,
        {"Accuracy": direct[:3] + [
            (model_a, "other", "third"),
            ("other", model_b, "third"),
            ("other", "third", "fourth"),
        ]},
        {"Accuracy": direct[3:], "Clarity": [("other", model_b, model_a)]},
    )

    accuracy = namespace["head_to_head_by_category"]["Accuracy"]
    assert accuracy.index.tolist() == [model_a, model_b]
    assert accuracy.to_dict("list") == {
        "wins_total": [3, 3], "wins_inclusive": [2, 1], "wins_general": [1, 2],
    }
    clarity = namespace["head_to_head_by_category"]["Clarity"]
    assert clarity.to_dict("list") == {
        "wins_total": [0, 1], "wins_inclusive": [0, 0], "wins_general": [0, 1],
    }
    overall = namespace["overall_head_to_head"]
    assert overall.to_dict("list") == {
        "wins_total": [3, 4], "wins_inclusive": [2, 1], "wins_general": [1, 3],
    }
    assert overall["wins_total"].equals(overall["wins_inclusive"] + overall["wins_general"])
    assert namespace["displayed"][::2] == ["### Accuracy", "### Clarity", "### Overall"]
    for dataset, output in zip(
        [accuracy, clarity, overall], namespace["displayed"][1::2],
    ):
        from matplotlib.colors import to_rgba

        assert len(output.axes) == 3
        colors = {model_a: to_rgba("tab:blue"), model_b: to_rgba("tab:orange")}
        for case_type, axis in zip(
            ("total", "inclusive", "general"), output.axes,
        ):
            wins = dataset[f"wins_{case_type}"].sort_values(
                ascending=False, kind="stable",
            )
            assert axis.get_title() == f"{case_type.title()} ({wins.sum()} comparisons)"
            if wins.sum() == 0:
                assert not axis.patches
                assert [text.get_text() for text in axis.texts] == ["No direct comparisons"]
                continue
            assert [text.get_text() for text in axis.get_legend().get_texts()] == [
                f"{model}: {count} wins" for model, count in wins.items()
            ]
            for wedge, (model, count) in zip(axis.patches, wins.items()):
                assert wedge.theta2 - wedge.theta1 == pytest.approx(
                    360 * count / wins.sum(), abs=0.001,
                )
                assert wedge.get_facecolor() == colors[model]
            assert [text.get_text() for text in axis.texts if text.get_text()] == [
                f"{100 * count / wins.sum():.1f}%" for count in wins if count > 0
            ]

    assert not namespace["plt"].get_fignums()

    reversed_models = namespace["head_to_head_dataset"](
        {"total": direct, "inclusive": [], "general": direct},
        (model_b, model_a),
    )
    assert reversed_models.index.tolist() == [model_b, model_a]
    assert reversed_models["wins_total"].tolist() == [3, 3]
    with pytest.raises(ValueError, match="two distinct models"):
        namespace["head_to_head_dataset"](
            {"total": [], "inclusive": [], "general": []}, (model_a, model_a),
        )


@pytest.mark.parametrize("inclusive", [
    {},
    {"Accuracy": [("Qwen/Qwen3-14B", "other", "third")]},
])
def test_head_to_head_reports_no_direct_comparisons(
    head_to_head_cell: str, inclusive: dict,
) -> None:
    namespace = run_head_to_head(head_to_head_cell, inclusive, {})

    assert namespace["overall_head_to_head"].to_dict("list") == {
        "wins_total": [0, 0], "wins_inclusive": [0, 0], "wins_general": [0, 0],
    }
    assert namespace["displayed"][-1] == (
        "No complete rankings directly comparing the selected models yet."
    )
    for figure in namespace["displayed"][1:-1:2]:
        assert len(figure.axes) == 3
        for axis in figure.axes:
            assert not axis.patches
            assert [text.get_text() for text in axis.texts] == ["No direct comparisons"]
