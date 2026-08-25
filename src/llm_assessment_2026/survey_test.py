"""Exercise a running Simple Survey instance through its UI and admin API."""

import json
import random
import secrets
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import click


COMMENT_ANSWERS = (
    "Automatski test rangira odgovore prema dužini prikazanog teksta.",
    "Rangiranje je generisano heuristikom zasnovanom na broju karaktera.",
    "Ovo je sintetički odgovor napravljen za proveru toka upitnika.",
)


def _request_json(
    method: str,
    url: str,
    admin_token: str,
    body: dict[str, object] | None = None,
    timeout: float = 30,
) -> Any:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {admin_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            response_body = response.read()
            return json.loads(response_body) if response_body else None
    except HTTPError as error:
        response_body = error.read().decode("utf-8", errors="replace")
        raise click.ClickException(
            f"Simple Survey API returned HTTP {error.code} for {url}: {response_body}"
        ) from error
    except URLError as error:
        raise click.ClickException(f"Could not reach Simple Survey at {url}: {error.reason}") from error


def _choice_value(choice: object) -> object:
    if isinstance(choice, dict):
        return choice["value"]
    return choice


def _select_participants_by_group(
    participants: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Select the first API participant for each non-null group value."""
    selected_by_group: dict[str, dict[str, Any]] = {}
    for participant in participants:
        variables = participant.get("variables")
        if not isinstance(variables, dict) or variables.get("group") is None:
            continue
        group_key = json.dumps(variables["group"], sort_keys=True)
        selected_by_group.setdefault(group_key, participant)
    return list(selected_by_group.values())


def _write_json(path: str, value: object) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return output_path


def _page_answers(
    questions: list[dict[str, Any]],
    response_features: list[dict[str, int]],
    randomizer: random.Random,
) -> dict[str, object]:
    answers: dict[str, object] = {}
    for question in questions:
        question_type = question["type"]
        question_name = question["name"]
        if question_type == "matrixdropdown":
            matrix_answer: dict[str, dict[str, object]] = {}
            columns = question["columns"]
            choices = [_choice_value(choice) for choice in columns[0]["choices"]]
            if len(choices) < len(columns):
                raise click.ClickException(
                    f"Question {question_name} does not have enough distinct choices."
                )
            if len(response_features) != len(choices):
                raise click.ClickException(
                    f"Question {question_name} has {len(choices)} choices but "
                    f"{len(response_features)} rendered responses."
                )

            tie_breakers = [randomizer.random() for _ in choices]
            ranked_choices = sorted(
                zip(choices, response_features, tie_breakers, strict=True),
                key=lambda item: (item[1]["character_count"], item[2]),
            )
            worst_choice = ranked_choices[0][0]
            best_choice = ranked_choices[-1][0]
            for row in question["rows"]:
                row_value = str(_choice_value(row))
                matrix_answer[row_value] = {
                    columns[0]["name"]: best_choice,
                    columns[1]["name"]: worst_choice,
                }
            answers[question_name] = matrix_answer
        elif question_type == "comment":
            answers[question_name] = randomizer.choice(COMMENT_ANSWERS)
        elif question.get("isRequired"):
            raise click.ClickException(
                f"Required question {question_name} has unsupported type {question_type}."
            )
    return answers


def _fill_page_controls(
    page: Any,
    questions: list[dict[str, Any]],
    answers: dict[str, object],
) -> None:
    dropdowns = page.locator(".sd-dropdown")
    comments = page.locator("textarea.sd-comment__input")
    dropdown_index = 0
    comment_index = 0

    for question in questions:
        question_name = question["name"]
        if question["type"] == "matrixdropdown":
            matrix_answer = answers[question_name]
            for row in question["rows"]:
                row_answer = matrix_answer[str(_choice_value(row))]
                for column in question["columns"]:
                    selected_value = row_answer[column["name"]]
                    selected_index = next(
                        index
                        for index, choice in enumerate(column["choices"])
                        if _choice_value(choice) == selected_value
                    )
                    dropdown = dropdowns.nth(dropdown_index)
                    dropdown.evaluate(
                        "(element) => element.scrollIntoView({block: 'center'})"
                    )
                    dropdown.click()
                    page.keyboard.press("Home")
                    for _ in range(selected_index + 1):
                        page.keyboard.press("ArrowDown")
                    page.keyboard.press("Enter")
                    dropdown_index += 1
        elif question["type"] == "comment":
            comment = comments.nth(comment_index)
            comment.evaluate("(element) => element.scrollIntoView({block: 'center'})")
            comment.fill(str(answers[question_name]))
            comment.press("Tab")
            comment_index += 1


def _page_snapshot(page: Any) -> dict[str, Any]:
    return page.evaluate(
        r"""
        () => ({
            name: survey.currentPage.name,
            pageNumber: survey.currentPageNo + 1,
            pageCount: survey.visiblePageCount,
            isLastPage: survey.isLastPage,
            questions: survey.currentPage.questions
                .filter((question) => question.isVisible)
                .map((question) => {
                    const definition = question.toJSON();
                    return {
                        name: question.name,
                        type: question.getType(),
                        isRequired: question.isRequired,
                        rows: definition.rows || [],
                        columns: definition.columns || [],
                    };
                }),
            responseFeatures: Array.from(
                document.querySelectorAll(
                    ".llm-response-panel .llm-response-content"
                )
            ).map((element) => {
                const text = (element.textContent || "")
                    .replace(/\s+/g, " ")
                    .trim();
                return {
                    character_count: text.length,
                    word_count: text ? text.split(" ").length : 0,
                };
            }),
        })
        """
    )


def _complete_survey_in_browser(
    survey_url: str,
    submit_url: str,
    randomizer: random.Random,
    headless: bool,
    timeout: float,
) -> tuple[dict[str, object], dict[str, object]]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise click.ClickException(
            "Playwright is not installed. Run 'uv sync' and retry."
        ) from error

    answers: dict[str, object] = {}
    ranking_features: dict[str, object] = {}
    timeout_ms = timeout * 1000
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=headless)
            try:
                page = browser.new_page()
                page.set_default_timeout(timeout_ms)
                page.goto(survey_url, wait_until="domcontentloaded")
                page.wait_for_function(
                    """() => typeof survey !== 'undefined' && (
                        survey.currentPage !== null ||
                        document.querySelector('#updateBtn')?.offsetParent !== null
                    )"""
                )
                page.evaluate("() => { Survey.settings.animationEnabled = false; }")
                update_button = page.locator("#updateBtn")
                if update_button.is_visible():
                    update_button.click()
                    page.wait_for_function("() => survey.currentPage !== null")

                while True:
                    snapshot = _page_snapshot(page)
                    page_answers = _page_answers(
                        snapshot["questions"],
                        snapshot["responseFeatures"],
                        randomizer,
                    )
                    answers.update(page_answers)
                    ranking_question = next(
                        question
                        for question in snapshot["questions"]
                        if question["type"] == "matrixdropdown"
                    )
                    ranking_features[snapshot["name"]] = {
                        "heuristic": "rendered_text_character_count",
                        "models": {
                            str(_choice_value(choice)): feature
                            for choice, feature in zip(
                                ranking_question["columns"][0]["choices"],
                                snapshot["responseFeatures"],
                                strict=True,
                            )
                        },
                    }
                    _fill_page_controls(
                        page,
                        snapshot["questions"],
                        page_answers,
                    )
                    if (
                        snapshot["pageNumber"] == 1
                        or snapshot["pageNumber"] % 10 == 0
                        or snapshot["isLastPage"]
                    ):
                        click.echo(
                            "  Completed page "
                            f"{snapshot['pageNumber']}/{snapshot['pageCount']}"
                        )

                    if snapshot["isLastPage"]:
                        with page.expect_response(
                            lambda response: response.url == submit_url
                            and response.request.method == "POST"
                        ) as response_info:
                            page.locator(".sd-navigation__complete-btn").click()
                        if not response_info.value.ok:
                            raise click.ClickException(
                                "Survey submission returned HTTP "
                                f"{response_info.value.status}."
                            )
                        break

                    page.locator(".sd-navigation__next-btn").click()
                    page.wait_for_function(
                        "(previousPage) => survey.currentPage.name !== previousPage",
                        arg=snapshot["name"],
                    )
            finally:
                browser.close()
    except PlaywrightError as error:
        message = str(error)
        if "Executable doesn't exist" in message:
            message = "Chromium is not installed. Run 'uv run playwright install chromium'."
        raise click.ClickException(message) from error

    return answers, ranking_features


def do_test_survey(
    base_url: str,
    admin_token: str,
    group: int | None,
    seed: int | None,
    output_file: str,
    responses_output_file: str,
    headless: bool,
    timeout: float,
) -> None:
    """Submit heuristic responses and verify them through the Simple Survey API."""
    base_url = base_url.rstrip("/")
    effective_seed = seed if seed is not None else secrets.randbits(64)
    randomizer = random.Random(effective_seed)
    created_participant_tokens: set[str] = set()
    deleted_participant_tokens: set[str] = set()
    if group is None:
        api_participants = _request_json(
            "GET",
            f"{base_url}/api/participants/",
            admin_token,
            timeout=timeout,
        )
        participants = _select_participants_by_group(api_participants)
        if not participants:
            raise click.ClickException(
                "The participants API returned no participants with a defined group variable."
            )
        click.echo(f"Testing one existing participant from each of {len(participants)} groups.")
    else:
        participant = _request_json(
            "POST",
            f"{base_url}/api/participants/",
            admin_token,
            {
                "label": f"Automated survey test (seed {effective_seed})",
                "variables": {"group": group},
            },
            timeout,
        )
        participants = [participant]
        created_participant_tokens.add(participant["token"])

    run_results: list[dict[str, Any]] = []
    responses: list[dict[str, Any]] | None = None
    try:
        for participant in participants:
            participant_token = participant["token"]
            participant_group = participant["variables"]["group"]
            survey_url = f"{base_url}/s/{participant_token}"
            submit_url = f"{base_url}/api/submit/{participant_token}"
            click.echo(
                f"Testing participant group {participant_group} "
                f"with seed {effective_seed}..."
            )
            answers, ranking_features = _complete_survey_in_browser(
                survey_url,
                submit_url,
                randomizer,
                headless,
                timeout,
            )
            run_results.append(
                {
                    "participant": participant,
                    "group": participant_group,
                    "answers": answers,
                    "ranking_features": ranking_features,
                }
            )

        responses = _request_json(
            "GET",
            f"{base_url}/api/responses",
            admin_token,
            timeout=timeout,
        )
    finally:
        for participant_token in created_participant_tokens:
            try:
                _request_json(
                    "DELETE",
                    f"{base_url}/api/participants/{participant_token}",
                    admin_token,
                    timeout=timeout,
                )
                deleted_participant_tokens.add(participant_token)
            except click.ClickException as cleanup_error:
                click.echo(
                    f"Warning: could not delete test participant: {cleanup_error}",
                    err=True,
                )

    responses_by_token = {response["token"]: response for response in responses}
    matched_responses = [
        responses_by_token[participant["token"]]
        for participant in participants
        if participant["token"] in responses_by_token
    ]
    _write_json(responses_output_file, matched_responses)
    report_runs = []
    all_verified = True
    for result in run_results:
        participant = result["participant"]
        stored_response = responses_by_token.get(participant["token"])
        verified = (
            stored_response is not None
            and stored_response["answers"] == result["answers"]
        )
        all_verified = all_verified and verified
        report_runs.append(
            {
                "group": result["group"],
                "participant": {
                    key: value for key, value in participant.items() if key != "token"
                },
                "answers": result["answers"],
                "ranking_features": result["ranking_features"],
                "verified": verified,
                "participant_source": (
                    "created" if participant["token"] in created_participant_tokens else "api"
                ),
                "participant_deleted": participant["token"] in deleted_participant_tokens,
            }
        )

    report = {
        "seed": effective_seed,
        "base_url": base_url,
        "runs": report_runs,
        "verified": all_verified,
        "responses_output_file": str(Path(responses_output_file)),
    }
    output_path = _write_json(output_file, report)
    if not all_verified:
        raise click.ClickException(
            f"Submitted answers did not match the API response. Report saved to {output_path}."
        )
    click.echo(f"Verified {len(report_runs)} participant responses through the API.")
    click.echo(f"Test report saved to {output_path}")
    click.echo(f"Literal API response saved to {responses_output_file}")