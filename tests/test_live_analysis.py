import json
from pathlib import Path

import pandas as pd
import pytest


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
