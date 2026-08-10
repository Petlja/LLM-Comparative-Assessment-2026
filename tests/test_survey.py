from types import SimpleNamespace

from llm_assessment_2026.survey import _build_comparison_page


def _entry(model: str, alias: str) -> tuple[SimpleNamespace, str, str]:
    metadata = SimpleNamespace(
        model=model,
        activity_url="https://example.com/lesson",
        activity_desc="Example lesson",
        prompt="Example prompt",
    )
    return metadata, alias, f"<p>{model} response</p>"


def test_comparison_page_is_scoped_to_group_and_uses_full_model_ids() -> None:
    page = _build_comparison_page(
        page_index=7,
        case_key="A1",
        entries=[
            _entry("provider/model-a", "A"),
            _entry("provider/model-b", "B"),
            _entry("other/model-c", "C"),
        ],
        group=3,
    )

    matrix = next(
        element for element in page["elements"] if element["type"] == "matrixdropdown"
    )
    presentation = next(
        element
        for element in page["elements"]
        if element["name"] == "page7_group03_responseComparison"
    )

    assert page["name"] == "page7_group03"
    assert page["visibleIf"] == "{group} = 3"
    assert presentation["html"].count('class="llm-response-panel"') == 3
    assert matrix["name"] == "A1__0__group-03__ranking"
    assert [row["value"] for row in matrix["rows"]] == ["q1", "q2", "q3", "q4"]
    assert [column["name"] for column in matrix["columns"]] == ["best", "worst"]
    assert [choice["value"] for choice in matrix["columns"][0]["choices"]] == [
        "provider/model-a",
        "provider/model-b",
        "other/model-c",
    ]
    assert "q1.best" in matrix["validators"][0]["expression"]
    assert "q4.worst" in matrix["validators"][0]["expression"]


def test_comment_question_is_unique_to_the_group() -> None:
    page = _build_comparison_page(
        page_index=8,
        case_key="A1",
        entries=[
            _entry("model-a", "A"),
            _entry("model-b", "B"),
            _entry("model-c", "C"),
        ],
        group=4,
    )

    comment = next(element for element in page["elements"] if element["type"] == "comment")
    assert comment["name"] == "A1__0__group-04__q5"