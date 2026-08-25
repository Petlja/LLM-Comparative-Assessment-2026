import random

import pytest
from click import ClickException

from llm_assessment_2026 import survey_test as survey_test_module
from llm_assessment_2026.survey_test import _page_answers, _select_participants_by_group


def test_page_answers_rank_responses_by_rendered_text_length() -> None:
    questions = [
        {
            "name": "case__ranking",
            "type": "matrixdropdown",
            "isRequired": True,
            "rows": [{"value": "q1"}, {"value": "q2"}],
            "columns": [
                {
                    "name": "best",
                    "choices": ["model-a", "model-b", "model-c"],
                },
                {
                    "name": "worst",
                    "choices": ["model-a", "model-b", "model-c"],
                },
            ],
        },
        {
            "name": "case__comment",
            "type": "comment",
            "isRequired": False,
        },
    ]

    response_features = [
        {"character_count": 100, "word_count": 20},
        {"character_count": 300, "word_count": 50},
        {"character_count": 200, "word_count": 35},
    ]
    answers = _page_answers(questions, response_features, random.Random(42))

    assert answers["case__comment"]
    for row in answers["case__ranking"].values():
        assert row == {"best": "model-b", "worst": "model-a"}


def test_page_answers_use_seed_only_to_break_length_ties() -> None:
    questions = [
        {
            "name": "case__ranking",
            "type": "matrixdropdown",
            "isRequired": True,
            "rows": [{"value": "q1"}],
            "columns": [
                {"name": "best", "choices": ["a", "b", "c"]},
                {"name": "worst", "choices": ["a", "b", "c"]},
            ],
        }
    ]
    tied_features = [
        {"character_count": 100, "word_count": 20},
        {"character_count": 100, "word_count": 20},
        {"character_count": 100, "word_count": 20},
    ]

    first = _page_answers(questions, tied_features, random.Random(42))
    second = _page_answers(questions, tied_features, random.Random(42))

    assert first == second
    ranking = first["case__ranking"]["q1"]
    assert ranking["best"] != ranking["worst"]


def test_page_answers_rejects_unsupported_required_question() -> None:
    questions = [
        {
            "name": "required-rating",
            "type": "rating",
            "isRequired": True,
        }
    ]

    with pytest.raises(ClickException, match="unsupported type rating"):
        _page_answers(questions, [], random.Random(1))


def test_select_participants_uses_first_participant_per_defined_group() -> None:
    participants = [
        {"token": "no-variables"},
        {"token": "no-group", "variables": {"school": "A"}},
        {"token": "null-group", "variables": {"group": None}},
        {"token": "group-1-first", "variables": {"group": 1}},
        {"token": "group-1-second", "variables": {"group": 1}},
        {"token": "group-2", "variables": {"group": 2}},
    ]

    selected = _select_participants_by_group(participants)

    assert [participant["token"] for participant in selected] == [
        "group-1-first",
        "group-2",
    ]


def test_explicit_group_saves_literal_api_response_and_deletes_participant(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    participant_token = "participant-secret"
    answers = {"case__comment": "Recorded answer"}
    api_calls = []

    def fake_request_json(method, url, admin_token, body=None, timeout=30):
        api_calls.append((method, url, admin_token, body, timeout))
        if method == "POST":
            return {
                "token": participant_token,
                "label": body["label"],
                "variables": body["variables"],
            }
        if method == "GET":
            return [
                {
                    "token": participant_token,
                    "label": "Automated survey test",
                    "answers": answers,
                }
            ]
        return None

    monkeypatch.setattr(survey_test_module, "_request_json", fake_request_json)
    monkeypatch.setattr(
        survey_test_module,
        "_complete_survey_in_browser",
        lambda *args: (
            answers,
            {
                "page1": {
                    "heuristic": "rendered_text_character_count",
                    "models": {},
                }
            },
        ),
    )
    output_file = tmp_path / "survey-test.json"
    responses_output_file = tmp_path / "survey-test-responces.json"

    survey_test_module.do_test_survey(
        "https://survey.example/",
        "admin-secret",
        group=2,
        seed=42,
        output_file=str(output_file),
        responses_output_file=str(responses_output_file),
        headless=True,
        timeout=15,
    )

    report_text = output_file.read_text(encoding="utf-8")
    report = survey_test_module.json.loads(report_text)
    literal_responses = survey_test_module.json.loads(
        responses_output_file.read_text(encoding="utf-8")
    )
    assert participant_token not in report_text
    assert "admin-secret" not in report_text
    assert "api_response" not in report
    assert report["runs"][0]["answers"] == answers
    assert report["runs"][0]["ranking_features"]["page1"]["heuristic"] == (
        "rendered_text_character_count"
    )
    assert report["verified"] is True
    assert report["runs"][0]["participant_source"] == "created"
    assert report["runs"][0]["participant_deleted"] is True
    assert literal_responses == [
        {
            "token": participant_token,
            "label": "Automated survey test",
            "answers": answers,
        }
    ]
    assert [(method, url) for method, url, *_ in api_calls] == [
        ("POST", "https://survey.example/api/participants/"),
        ("GET", "https://survey.example/api/responses"),
        ("DELETE", f"https://survey.example/api/participants/{participant_token}"),
    ]


def test_omitted_group_tests_one_existing_participant_per_group(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    participants = [
        {"token": "group-1-first", "label": "One", "variables": {"group": 1}},
        {"token": "group-1-second", "label": "Duplicate", "variables": {"group": 1}},
        {"token": "ignored", "label": "No group", "variables": {}},
        {"token": "group-2", "label": "Two", "variables": {"group": 2}},
    ]
    answers_by_token = {
        "group-1-first": {"group-1": "answer"},
        "group-2": {"group-2": "answer"},
    }
    api_responses = [
        {"token": token, "label": token, "answers": answers}
        for token, answers in answers_by_token.items()
    ] + [{"token": "unrelated", "label": "Other", "answers": {}}]
    api_calls = []

    def fake_request_json(method, url, admin_token, body=None, timeout=30):
        api_calls.append((method, url))
        if url.endswith("/api/participants/"):
            return participants
        if url.endswith("/api/responses"):
            return api_responses
        raise AssertionError(f"Unexpected API call: {method} {url}")

    def fake_complete(survey_url, *args):
        participant_token = survey_url.rsplit("/", 1)[-1]
        return answers_by_token[participant_token], {}

    monkeypatch.setattr(survey_test_module, "_request_json", fake_request_json)
    monkeypatch.setattr(
        survey_test_module,
        "_complete_survey_in_browser",
        fake_complete,
    )
    output_file = tmp_path / "survey-test.json"
    responses_output_file = tmp_path / "survey-test-responces.json"

    survey_test_module.do_test_survey(
        "https://survey.example",
        "admin-secret",
        group=None,
        seed=42,
        output_file=str(output_file),
        responses_output_file=str(responses_output_file),
        headless=True,
        timeout=15,
    )

    report = survey_test_module.json.loads(output_file.read_text(encoding="utf-8"))
    assert [run["group"] for run in report["runs"]] == [1, 2]
    assert all(run["participant_source"] == "api" for run in report["runs"])
    assert all(run["participant_deleted"] is False for run in report["runs"])
    assert report["verified"] is True
    assert survey_test_module.json.loads(
        responses_output_file.read_text(encoding="utf-8")
    ) == api_responses[:2]
    assert api_calls == [
        ("GET", "https://survey.example/api/participants/"),
        ("GET", "https://survey.example/api/responses"),
    ]