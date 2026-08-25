"""CLI entrypoint for llmcmp."""

import click

from .cases import do_check_cases
from .survey import do_survey
from .survey_test import do_test_survey


class OrderedGroup(click.Group):
    """A Click group that lists commands in registration order."""

    def list_commands(self, ctx: click.Context) -> list[str]:
        return list(self.commands)


@click.group(cls=OrderedGroup)
def main() -> None:
    """LLM Comparative Assessment 2026 CLI."""
    pass


@main.command(name="check_cases")
@click.option(
    "--cases",
    "-c",
    default="eval/test-cases.yml",
    type=click.Path(exists=True),
    help="Path to the test cases YAML file.",
)
def check_cases(cases: str) -> None:
    """Validate the test case definitions of this assessment round."""
    do_check_cases(cases)


@main.command()
@click.option(
    "--survey-file",
    "-s",
    default="eval/output/survey.json",
    type=click.Path(dir_okay=False),
    help="Path of the generated survey definition.",
)
def survey(survey_file: str) -> None:
    """Generate the SurveyJS survey definition from inference outputs."""
    do_survey(survey_file)


@main.command(name="test_survey")
@click.option(
    "--base-url",
    default="http://127.0.0.1:5000",
    show_default=True,
    help="Base URL of a running Simple Survey instance.",
)
@click.option(
    "--admin-token",
    envvar="SIMPLE_SURVEY_ADMIN_TOKEN",
    required=True,
    help="Simple Survey admin token (or set SIMPLE_SURVEY_ADMIN_TOKEN).",
)
@click.option(
    "--group",
    type=click.IntRange(min=1),
    help=(
        "Create a temporary participant for this group. When omitted, test one "
        "existing API participant per defined group."
    ),
)
@click.option(
    "--seed",
    type=int,
    help="Seed for length ties and synthetic comments; generated when omitted.",
)
@click.option(
    "--output-file",
    default="eval/output/survey-test.json",
    show_default=True,
    type=click.Path(dir_okay=False),
    help="Path for generated answers, features, and verification metadata.",
)
@click.option(
    "--responses-output-file",
    default="eval/output/survey-test-responces.json",
    show_default=True,
    type=click.Path(dir_okay=False),
    help="Path for the literal response returned by the responses API.",
)
@click.option(
    "--headless/--headed",
    default=True,
    show_default=True,
    help="Run Chromium without or with a visible window.",
)
@click.option(
    "--timeout",
    type=click.FloatRange(min=1),
    default=30.0,
    show_default=True,
    help="Timeout in seconds for browser and API operations.",
)
def test_survey(
    base_url: str,
    admin_token: str,
    group: int | None,
    seed: int | None,
    output_file: str,
    responses_output_file: str,
    headless: bool,
    timeout: float,
) -> None:
    """Submit and verify heuristic answers through Simple Survey."""
    do_test_survey(
        base_url,
        admin_token,
        group,
        seed,
        output_file,
        responses_output_file,
        headless,
        timeout,
    )


if __name__ == "__main__":
    main()
