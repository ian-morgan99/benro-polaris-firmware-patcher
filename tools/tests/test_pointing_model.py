import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "container/astro/ondisk/polaris-pointing-model.sh"


def run(env, *args):
    return subprocess.run(
        ["sh", str(HELPER), *args],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def test_pointing_model_records_and_predicts_opposite_residual(tmp_path):
    env = os.environ.copy()
    env.update(
        {
            "POINTING_MODEL_OBS": str(tmp_path / "observations.tsv"),
            "POINTING_MODEL_FILE": str(tmp_path / "model.json"),
            "POINTING_MODEL_MIN_SAMPLES": "3",
            "POINTING_MODEL_MAX_OFFSET_DEG": "2.0",
        }
    )

    # solved - requested is +0.1 RA tangent-plane and +0.2 Dec. A future
    # command must therefore subtract those means.
    for target_ra, target_dec in ((10, 20), (40, 20), (80, 20)):
        run(env, "record", str(target_ra), str(target_dec),
            str(target_ra + 0.1), str(target_dec + 0.2), "0")

    model = json.loads(run(env, "status").stdout)
    assert model["samples"] == 3
    assert abs(model["mean_ddec_deg"] - 0.2) < 1e-6

    predicted = run(env, "predict", "120", "20").stdout.split()
    assert abs(float(predicted[1]) - 19.8) < 1e-6
    # At the same declination the tangent-plane conversion returns the
    # measured 0.1-degree RA correction; a different declination would scale
    # it by the ratio of cosines.
    assert abs(float(predicted[0]) - 119.9) < 1e-6


def test_pointing_model_does_not_predict_before_minimum_samples(tmp_path):
    env = os.environ.copy()
    env.update(
        {
            "POINTING_MODEL_OBS": str(tmp_path / "observations.tsv"),
            "POINTING_MODEL_FILE": str(tmp_path / "model.json"),
            "POINTING_MODEL_MIN_SAMPLES": "3",
        }
    )
    run(env, "record", "10", "20", "10.1", "20.2", "0")
    result = subprocess.run(
        ["sh", str(HELPER), "predict", "120", "20"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
