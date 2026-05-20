import os
import shutil
import subprocess
import tempfile
import zipapp
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLI_NAME = "tests_cli.pyz"
CLI_DIR = REPO_ROOT / "tests" / "cli"
DIST_DIR = REPO_ROOT / "dist"
PYZ_OUTPUT = DIST_DIR / CLI_NAME


@pytest.fixture(scope="session")
def sample_cli_pyz():
    DIST_DIR.mkdir(exist_ok=True)

    subprocess.run(
        ["poetry", "build", "-f", "wheel"],
        cwd=REPO_ROOT, check=True, capture_output=True
    )

    wheels = sorted(DIST_DIR.glob("*.whl"), key=os.path.getmtime, reverse=True)
    if not wheels:
        raise RuntimeError("No wheel found in dist/ after poetry build")
    wheel = wheels[0]

    with tempfile.TemporaryDirectory(prefix="cli_pyz_") as tmpdir:
        tmp_path = Path(tmpdir)
        subprocess.run(
            ["pip", "install", "--target", str(tmp_path), "--no-compile", "--upgrade", str(wheel)],
            check=True, capture_output=True
        )

        pkg_dir = tmp_path / "tests" / "cli"
        pkg_dir.mkdir(parents=True)
        (tmp_path / "tests" / "__init__.py").touch()
        (tmp_path / "tests" / "cli" / "__init__.py").touch()
        shutil.copy2(CLI_DIR / "__main__.py", pkg_dir / "__main__.py")
        shutil.copy2(CLI_DIR / "sample_command.py", pkg_dir / "sample_command.py")

        zipapp.create_archive(
            str(tmp_path),
            str(PYZ_OUTPUT),
            main="tests.cli.__main__:cli",
            compressed=True,
        )

        size_mb = os.path.getsize(PYZ_OUTPUT) / (1024 * 1024)
        print(f"\n[CLI] Built {CLI_NAME} size: {size_mb:.1f} MB", flush=True)

        yield str(PYZ_OUTPUT)

    PYZ_OUTPUT.unlink(missing_ok=True)
