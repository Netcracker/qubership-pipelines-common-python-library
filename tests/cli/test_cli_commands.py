import os
import subprocess

import pytest
import yaml

SAMPLE_DATA_DIR = os.path.join(os.path.dirname(__file__), "sample_data")


@pytest.mark.cli
def test_help(sample_cli_pyz):
    result = subprocess.run(
        ["python", sample_cli_pyz, "--help"],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "Commands:" in result.stdout


@pytest.mark.cli
def test_run_via_inline_params(sample_cli_pyz):
    result = subprocess.run(
        ["python", sample_cli_pyz, "calc",
         "-p", "params.param_1=9",
         "-p", "params.param_2=10",
         "--cli-output-mode=INSECURE_PARAMS"],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    parsed = yaml.safe_load(result.stdout)
    assert parsed["params"]["result"] == 19


@pytest.mark.cli
def test_run_via_context_file(sample_cli_pyz):
    context_path = os.path.join(SAMPLE_DATA_DIR, "context.yaml")
    result_path = os.path.join(SAMPLE_DATA_DIR, "result.yaml")

    if os.path.exists(result_path):
        os.remove(result_path)

    result = subprocess.run(
        ["python", sample_cli_pyz, "calc",
         f"--context_path={context_path}"],
        capture_output=True, text=True
    )
    assert result.returncode == 0

    assert os.path.exists(result_path)
    with open(result_path) as f:
        parsed = yaml.safe_load(f)
    assert parsed["params"]["result"] == 19

    os.remove(result_path)


@pytest.mark.cli
def test_run_via_inline_params_merged(sample_cli_pyz):
    result = subprocess.run(
        ["python", sample_cli_pyz, "calc",
         "-p", "params.param_1=9",
         "-s", "params.param_2=11",
         "--cli-output-mode=MERGED_PARAMS"],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    parsed = yaml.safe_load(result.stdout)
    assert parsed["params"]["result"] == 20
    assert parsed["kind"] == "AtlasModuleParamsSecure" # due to merge


@pytest.mark.cli
def test_run_via_inline_params_with_folder_path(sample_cli_pyz):
    result = subprocess.run(
        ["python", sample_cli_pyz, "calc",
         "-p", "params.param_1=9",
         "-p", "params.param_2=10",
         "--folder_path=./test_output"],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    output_path = os.path.join("test_output", "output", "params.yaml")
    with open(output_path) as f:
        parsed = yaml.safe_load(f)
    assert parsed["params"]["result"] == 19
