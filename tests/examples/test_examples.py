# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

"""End-to-end smoke tests for the scripts under ``examples/``.

Each example is invoked the same way a user invokes it
(``python examples/<script>.py ...``) against a small generated instance.
The goal is to catch breakages that pure unit tests miss — things like
the abstract-class instantiation bug that broke ``solve_instance.py``
after the solver-factory refactor, or the renamed
``StochasticSolver(T=..., B=...)`` parameters that broke
``live_update.py``.

The tests deliberately go through a subprocess so argparse, stdout
formatting, and module-load behavior are exercised exactly as a user
would see them.
"""

from __future__ import annotations

import contextlib
import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "examples"


def _run(
    *args: str,
    cwd: Path,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    """Run a Python script in a subprocess with a headless matplotlib backend.

    Raises CalledProcessError on non-zero exit (so the test fails) and
    TimeoutExpired if the script doesn't exit within ``timeout`` seconds.
    """
    env = os.environ.copy()
    env["MPLBACKEND"] = "Agg"
    return subprocess.run(
        [sys.executable, *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
    )


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    """A tmp working directory with an empty ``data/`` subdir for output."""
    (tmp_path / "data").mkdir()
    return tmp_path


@pytest.fixture()
def instance_file(workspace: Path) -> Path:
    """Generate one easy instance in ``workspace/data`` and return its path."""
    _run(
        str(EXAMPLES / "generate_instances.py"),
        "-c",
        "easy",
        "-s",
        "42",
        "-n",
        "1",
        "-o",
        str(workspace / "data"),
        cwd=workspace,
    )
    path = workspace / "data" / "instance_0.json"
    assert path.exists()
    return path


@pytest.fixture()
def instance_files(workspace: Path) -> list[Path]:
    """Generate four instances so ``live_update``'s hardcoded
    ``data/instance_3.json`` exists."""
    _run(
        str(EXAMPLES / "generate_instances.py"),
        "-c",
        "easy",
        "-s",
        "7",
        "-n",
        "4",
        "-o",
        str(workspace / "data"),
        cwd=workspace,
    )
    return [workspace / "data" / f"instance_{i}.json" for i in range(4)]


# ---- generate_instances.py --------------------------------------------------


def test_generate_instances_writes_json(workspace: Path) -> None:
    """generate_instances.py emits the requested number of instances."""
    _run(
        str(EXAMPLES / "generate_instances.py"),
        "-c",
        "easy",
        "-s",
        "1",
        "-n",
        "2",
        "-o",
        str(workspace / "out"),
        cwd=workspace,
    )
    assert (workspace / "out" / "instance_0.json").exists()
    assert (workspace / "out" / "instance_1.json").exists()


# ---- solve_instance.py ------------------------------------------------------


def test_solve_instance_dummy_runs(
    workspace: Path, instance_file: Path
) -> None:
    """solve_instance.py runs end-to-end with the dummy solver, no Gantt."""
    _run(
        str(EXAMPLES / "solve_instance.py"),
        "-i",
        str(instance_file),
        "-s",
        "dummy",
        cwd=workspace,
    )


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_solve_instance_renders_gantt(
    workspace: Path, instance_file: Path, theme: str
) -> None:
    """``-g`` produces a Gantt PNG in either theme."""
    _run(
        str(EXAMPLES / "solve_instance.py"),
        "-i",
        str(instance_file),
        "-s",
        "dummy",
        "-g",
        "-t",
        theme,
        cwd=workspace,
    )
    assert (workspace / "data" / "gantt_chart.png").exists()


@pytest.mark.parametrize("idle", ["hide", "compress", "show"])
def test_solve_instance_idle_modes(
    workspace: Path, instance_file: Path, idle: str
) -> None:
    """All three ``--idle`` modes produce a chart without errors."""
    _run(
        str(EXAMPLES / "solve_instance.py"),
        "-i",
        str(instance_file),
        "-s",
        "dummy",
        "-g",
        "--idle",
        idle,
        cwd=workspace,
    )
    assert (workspace / "data" / "gantt_chart.png").exists()


def test_solve_instance_annotations_and_flags(
    workspace: Path, instance_file: Path
) -> None:
    """``--annotation`` and ``--no-utilization`` are accepted and applied."""
    _run(
        str(EXAMPLES / "solve_instance.py"),
        "-i",
        str(instance_file),
        "-s",
        "dummy",
        "-g",
        "--annotation",
        "30:start",
        "--annotation",
        "120:review:#9B59B6",
        "--no-utilization",
        cwd=workspace,
    )
    assert (workspace / "data" / "gantt_chart.png").exists()


# ---- visualize_instance.py --------------------------------------------------


def test_visualize_instance_emits_dot(
    workspace: Path, instance_file: Path
) -> None:
    """visualize_instance.py prints a DOT graph when no output path is given."""
    result = _run(
        str(EXAMPLES / "visualize_instance.py"),
        "-i",
        str(instance_file),
        cwd=workspace,
    )
    assert "digraph" in result.stdout


def test_visualize_instance_writes_dot_file(
    workspace: Path, instance_file: Path
) -> None:
    """When ``-o foo.dot`` is given, the DOT string is written to disk."""
    out = workspace / "instance.dot"
    _run(
        str(EXAMPLES / "visualize_instance.py"),
        "-i",
        str(instance_file),
        "-o",
        str(out),
        cwd=workspace,
    )
    assert out.exists()
    assert "digraph" in out.read_text()


# ---- overrun_demo.py --------------------------------------------------------


def test_overrun_demo_saves_image(workspace: Path) -> None:
    """overrun_demo.py renders the synthetic demo and saves it to disk."""
    out = workspace / "overrun.png"
    _run(
        str(EXAMPLES / "overrun_demo.py"),
        "--save",
        str(out),
        cwd=workspace,
    )
    assert out.exists()
    assert out.stat().st_size > 0


# ---- live_update.py ---------------------------------------------------------


def test_live_update_module_imports() -> None:
    """live_update.py imports cleanly.

    The script body itself runs an interactive event loop that's not
    suitable for CI; the runtime test below covers the actual main()
    behavior. This faster check still catches plain syntax / import
    breakages.
    """
    # Reload so the module body executes at module level.
    sys.modules.pop("examples.live_update", None)
    importlib.import_module("examples.live_update")


def test_live_update_starts_without_construction_errors(
    workspace: Path, instance_files: list[Path]
) -> None:
    """live_update.py starts and gets past solver/executor construction.

    The simulation loop runs indefinitely (until manually stopped), so we
    bound it with a timeout and treat TimeoutExpired as success: the script
    survived past the early ``StochasticSolver(...)`` / ``DynamicExecutor(...)``
    calls that previous refactors have broken. A non-zero exit before the
    timeout — which is what an API-drift bug looks like — fails the test.
    """
    try:
        _run(str(EXAMPLES / "live_update.py"), cwd=workspace, timeout=8)
    except subprocess.TimeoutExpired:
        # expected; the sim doesn't self-terminate quickly
        contextlib.suppress(subprocess.TimeoutExpired)
