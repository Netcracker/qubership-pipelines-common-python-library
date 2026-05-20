import click
from qubership_pipelines_common_library.v1.utils.utils_cli import utils_cli

from tests.cli.sample_command import SampleExecutionCommand


@click.group(chain=True)
def cli():
    pass


@cli.command("calc")
@utils_cli
def __calc(**kwargs):
    command = SampleExecutionCommand(**kwargs)
    command.run()
