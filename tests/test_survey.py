from types import SimpleNamespace

from llm_assessment_2026.survey import _build_ranking_page


def _entry(model: str, alias: str) -> tuple[SimpleNamespace, str, str]:
    metadata = SimpleNamespace(
        model=model,
        activity_url="https://example.com/lesson",
        activity_desc="Example lesson",
        prompt="Example prompt",
    )
    return metadata, alias, f"<p>{model} response</p>"


def test_ranking_page_is_scoped_to_group_and_uses_full_model_ids() -> None:
    page = _build_ranking_page(
        page_index=7,
        case_key="A1",
        entries=[
            _entry("provider/model-a", "A"),
            _entry("provider/model-b", "B"),
            _entry("other/model-c", "C"),
        ],
        group=3,
        question_id="q1",
        category_title="Category",
    )

    ranking = next(element for element in page["elements"] if element["type"] == "ranking")

    assert page["name"] == "page7_group03"
    assert page["visibleIf"] == "{group} = 3"
    assert ranking["name"] == "A1__0__group-03__q1"
    assert [choice["value"] for choice in ranking["choices"]] == [
        "provider/model-a",
        "provider/model-b",
        "other/model-c",
    ]


def test_comment_question_is_unique_to_the_group() -> None:
    page = _build_ranking_page(
        page_index=8,
        case_key="A1",
        entries=[
            _entry("model-a", "A"),
            _entry("model-b", "B"),
            _entry("model-c", "C"),
        ],
        group=4,
        question_id="q4",
        category_title="Overall",
    )

    comment = next(element for element in page["elements"] if element["type"] == "comment")
    assert comment["name"] == "A1__0__group-04__q5"