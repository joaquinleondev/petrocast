"""CLI smokes: evaluation artifacts, stdout contract and gate exit codes.

The success-path smoke asserts *consistency* (exit code mirrors the verdict,
JSON on disk mirrors stdout) because the real-model verdict on fixtures is
data-dependent. The failure path is forced deterministically: test-month
actuals are rewritten to equal each well's last pre-cutoff value, making the
persistence naive perfect (aggregate naive MAE = 0), which an imperfect model
cannot match — gate 2 must fail and the CLI must exit 1.
"""

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from petrocast_ml.evaluation import EVALUATION_FILE

CUTOFF = pd.Timestamp("2026-01-01")


def _run_cli(fixtures: Path, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "petrocast_ml.training",
            "--features-csv",
            str(fixtures / "well_features.csv"),
            "--production-csv",
            str(fixtures / "production_monthly.csv"),
            "--as-of",
            "2026-01-01",
            "--horizons",
            "1,2,3",
            "--output-dir",
            str(tmp_path / "artifact"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_writes_report_and_exit_code_mirrors_verdict(
    fixtures_dir: Path, tmp_path: Path
) -> None:
    completed = _run_cli(fixtures_dir, tmp_path)
    payload = json.loads(completed.stdout)

    report_path = Path(payload["artifact_dir"]) / EVALUATION_FILE
    assert report_path.exists()
    assert json.loads(report_path.read_text()) == payload["evaluation"]
    assert payload["gates_passed"] is payload["evaluation"]["gates_passed"]
    assert completed.returncode == (0 if payload["gates_passed"] else 1), completed.stderr


def test_cli_exits_1_when_the_naive_is_unbeatable(
    fixtures_dir: Path, production_monthly: pd.DataFrame, tmp_path: Path
) -> None:
    last_before_cutoff = (
        production_monthly.loc[production_monthly["production_month"] < CUTOFF]
        .sort_values("production_month")
        .groupby("well_id")["oil_prod_m3"]
        .last()
    )
    rigged = production_monthly.copy()
    test_rows = rigged["production_month"] >= CUTOFF
    rigged.loc[test_rows, "oil_prod_m3"] = (
        rigged.loc[test_rows, "well_id"].map(last_before_cutoff).to_numpy()
    )

    rigged_dir = tmp_path / "rigged"
    rigged_dir.mkdir()
    rigged.to_csv(rigged_dir / "production_monthly.csv", index=False)
    (rigged_dir / "well_features.csv").write_text((fixtures_dir / "well_features.csv").read_text())

    completed = _run_cli(rigged_dir, tmp_path)
    payload = json.loads(completed.stdout)
    assert payload["gates_passed"] is False
    assert completed.returncode == 1
