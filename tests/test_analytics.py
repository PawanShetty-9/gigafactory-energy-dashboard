"""Unit tests for the analytics engine, run on a freshly generated offline dataset."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.fetch_and_generate import build_dataset, generate_synthetic_market  # noqa: E402
from utils import analytics as an  # noqa: E402


@pytest.fixture(scope="module")
def dataset():
    data, meta = build_dataset(days=60, offline=True, seed=42)
    return an.add_cost_columns(data), meta


def test_dataset_shape_and_scale(dataset):
    df, _ = dataset
    assert len(df) == 60 * 24
    assert 35 <= df["electricity_mwh"].mean() <= 60  # ~40-60 MW Gigafactory
    assert df["production_units"].min() >= 0
    assert not df.isna().any().any()


def test_kpis_are_consistent(dataset):
    df, _ = dataset
    k = an.compute_kpis(df)
    assert k["energy_mwh"] == pytest.approx(df["electricity_mwh"].sum() + df["gas_mwh"].sum())
    assert k["intensity_kwh_unit"] == pytest.approx(k["energy_mwh"] * 1000 / k["units"])


def test_leak_is_detected(dataset):
    df, _ = dataset
    anomalies = an.detect_anomalies(df, method="zscore", threshold=3.5)
    injected = df["leak_injected"]
    hits = (anomalies["is_anomaly"] & injected).sum()
    assert hits / injected.sum() > 0.9  # recall
    assert hits / max(anomalies["is_anomaly"].sum(), 1) > 0.9  # precision
    events = an.summarize_anomalies(df, anomalies)
    assert events.iloc[0]["weekend_hours"] > 0
    assert events["wasted_mwh"].sum() > 0


def test_isolation_forest_finds_the_leak(dataset):
    df, _ = dataset
    anomalies = an.detect_anomalies(df, method="isolation_forest", contamination=0.06)
    assert (anomalies["is_anomaly"] & df["leak_injected"]).sum() > 0.5 * df["leak_injected"].sum()


def test_load_shift_saves_money_without_new_peak(dataset):
    df, _ = dataset
    result = an.optimize_load_shift(df, 0.10, float(df["price_eur_mwh"].median()))
    assert result.cost_saving_eur > 0
    assert result.peak_after_mw <= result.peak_before_mw + 1e-9
    # Energy is conserved apart from storage losses
    assert result.profile["shifted_mw"].sum() >= result.profile["original_mw"].sum()
    assert an.optimize_load_shift(df, 0.0, 100.0).cost_saving_eur == 0


def test_mv_recovers_the_18_percent_saving(dataset):
    df, meta = dataset
    mv = an.measurement_and_verification(df, pd.Timestamp(meta["events"]["heat_recovery_go_live"]))
    assert mv.savings_pct == pytest.approx(18, abs=1.5)
    assert mv.cv_rmse < 25 and abs(mv.nmbe) < 10
    # CUSUM is flat before go-live and falls after it
    base = mv.daily[mv.daily["period"] == "baseline"]["cusum"]
    rep = mv.daily[mv.daily["period"] == "reporting"]["cusum"]
    assert abs(base.iloc[-1]) < 0.05 * abs(rep.iloc[-1])
    assert np.all(np.diff(rep.values) < 0)


def test_synthetic_market_has_realistic_ranges():
    idx = pd.date_range("2026-01-01", periods=24 * 30, freq="h", tz=an.TZ)
    market = generate_synthetic_market(idx, np.random.default_rng(1))
    assert market["renewable_share_pct"].between(0, 100).all()
    assert market["price_eur_mwh"].between(-500, 500).all()
