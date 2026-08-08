"""CLI entrypoint for llmcmp."""

import click

from .cases import do_check_cases
from .survey import do_survey


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


if __name__ == "__main__":
    main()
