import json
from datetime import datetime
from io import StringIO
from pathlib import Path
from urllib.request import Request

import pandas as pd
import pytest


@pytest.mark.parametrize("initial_responses", [
    [],
    [{"label": "p01", "answers": {"q1": "Odgovor čćš"}},
     {"label": "test01", "answers": {"q1": "synthetic"}}],
])
def test_fetch_saves_raw_responses_and_overwrites_same_minute(
    tmp_path: Path, monkeypatch, initial_responses: list[dict],
) -> None:
    notebook_path = Path(__file__).parents[1] / "suvrey-analisys" / "live-analisys.ipynb"
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    source = "".join(notebook["cells"][2]["source"])
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

    class FixedDatetime:
        @staticmethod
        def now() -> datetime:
            return datetime(2026, 10, 9, 13, 3)

    def urlopen(request: Request, timeout: int) -> StringIO:
        assert timeout == 30
        calls.append(request.full_url)
        data = participants if request.full_url.endswith("/api/participants/") else raw_responses
        return StringIO(json.dumps(data))

    def limit_response_cases(responses, survey_path, n_cases):
        limited_responses.append(responses)
        return []

    namespace = {
        "json": json, "datetime": FixedDatetime, "Path": Path, "pd": pd,
        "Request": Request, "urlopen": urlopen,
        "limit_response_cases": limit_response_cases,
    }
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
        ]
    assert calls == ["http://localhost/api/responses", "http://localhost/api/participants/"] * 2


@pytest.fixture
def timeline_cell() -> str:
    notebook_path = (
        Path(__file__).parents[1] / "suvrey-analisys" / "live-analisys.ipynb"
    )
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    cell = notebook["cells"][-1]
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
        {"token": "selected", "label": "p07"},
        {"token": "excluded", "label": "p08"},
    ]
    questions = [
        {"token": "selected", "question_name": "later", "first_answered_at": "2026-10-06T12:00:00"},
        {"token": "excluded", "question_name": "other", "first_answered_at": "2026-10-06T09:00:00"},
        {"token": "selected", "question_name": "earlier", "first_answered_at": "2026-10-06T10:00:00.123000"},
        {"token": "selected", "question_name": "same_time", "first_answered_at": "2026-10-06T10:00:00.123000"},
    ]

    namespace = run_timeline(timeline_cell, questions, participants)
    timeline = namespace["question_timeline"]

    assert namespace["timeline_participant"] == "p07"
    assert list(timeline.columns) == ["question_name", "first_answered_at"]
    assert timeline["question_name"].tolist() == ["earlier", "same_time", "later"]
    assert str(timeline["first_answered_at"].dt.tz) == "UTC"
    assert isinstance(namespace["displayed"][-1], pd.DataFrame)
    assert namespace["displayed"][-1]["first_answered_at"].tolist() == [
        "2026-10-06 10:00",
        "2026-10-06 10:00",
        "2026-10-06 12:00",
    ]


def test_timeline_reports_no_records(timeline_cell: str) -> None:
    namespace = run_timeline(
        timeline_cell, [], [{"token": "selected", "label": "p07"}],
    )

    assert namespace["question_timeline"].empty
    assert namespace["displayed"][-1] == "No question timestamps recorded for this participant."


@pytest.mark.parametrize("participants", [
    [],
    [{"token": "a", "label": "p07"}, {"token": "b", "label": "p07"}],
])
def test_timeline_rejects_missing_or_ambiguous_participant(
    timeline_cell: str, participants: list[dict],
) -> None:
    with pytest.raises(ValueError, match="Expected one participant labelled 'p07'"):
        run_timeline(timeline_cell, [], participants)


def test_timeline_rejects_invalid_timestamp(timeline_cell: str) -> None:
    with pytest.raises(ValueError):
        run_timeline(
            timeline_cell,
            [{"token": "selected", "question_name": "ranking", "first_answered_at": "invalid"}],
            [{"token": "selected", "label": "p07"}],
        )


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
        "rank_borda": survey_responce.rank_borda,
        "rank_plackett_luce": survey_responce.rank_plackett_luce,
        "rank_by_category": survey_responce.rank_by_category,
        "rank_overall": survey_responce.rank_overall,
        "Markdown": str, "display": displayed.append,
    }

    exec(compile(source, "live-analisys.ipynb:rankings", "exec"), namespace)

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
