"""
Analytics engine for the Gigafactory Energy & Flexibility Analytics Dashboard.

Contents
--------
* Data loading & KPI calculation (energy, cost, CO2, energy intensity)
* Baseload / load profile analysis (Lastganganalyse, Grundlast)
* Anomaly detection for compressed air leaks (robust Z-score on model residuals,
  or Isolation Forest)
* Load-shifting optimizer for day-ahead price flexibility (Lastverschiebung)
* Measurement & Verification (M&V) of energy efficiency projects following the
  IPMVP Option C regression approach with ASHRAE Guideline 14 statistics and CUSUM,
  as used for ISO 50001 EnPI/EnB reporting and EMAS environmental statements.

All functions are pure (DataFrame in -> DataFrame/dict out) so they can be unit
tested and cached by Streamlit.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

TZ = "Europe/Berlin"
ROOT = Path(__file__).resolve().parents[1]
DATA_CSV = ROOT / "data" / "factory_energy_data.csv"
METADATA_JSON = ROOT / "data" / "metadata.json"

GAS_EMISSION_FACTOR = 0.201  # t CO2 / MWh natural gas (UBA, rounded)

UTILITY_COLUMNS = {
    "electricity": "electricity_mwh",
    "gas": "gas_mwh",
    "compressed_air": "compressed_air_mwh",
    "cooling": "cooling_water_mwh_th",
    "heating": "heating_water_mwh_th",
}


# ======================================================================================
# Loading
# ======================================================================================
def load_dataset(path: Path = DATA_CSV) -> pd.DataFrame:
    """Load the processed dataset with a tz-aware Europe/Berlin hourly index."""
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `python data/fetch_and_generate.py` to create it."
        )
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(TZ)
    df = df.set_index("timestamp").sort_index()
    for col in ("leak_injected", "post_heat_recovery"):
        if col in df:
            df[col] = df[col].astype(str).str.lower().eq("true")
    return add_cost_columns(df)


def load_metadata(path: Path = METADATA_JSON) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def add_cost_columns(
    df: pd.DataFrame, grid_fees_eur_mwh: float = 65.0, gas_price_eur_mwh: float = 42.0
) -> pd.DataFrame:
    """
    Electricity is priced as day-ahead spot (pass-through contract) + network charges,
    levies and electricity tax; gas at a flat procurement price incl. CO2 cost.
    """
    df = df.copy()
    df["electricity_cost_eur"] = df["electricity_mwh"] * (df["price_eur_mwh"] + grid_fees_eur_mwh)
    df["gas_cost_eur"] = df["gas_mwh"] * gas_price_eur_mwh
    df["energy_cost_eur"] = df["electricity_cost_eur"] + df["gas_cost_eur"]
    df["co2_electricity_t"] = df["electricity_mwh"] * df["grid_co2_t_per_mwh"]
    df["co2_gas_t"] = df["gas_mwh"] * GAS_EMISSION_FACTOR
    df["co2_t"] = df["co2_electricity_t"] + df["co2_gas_t"]
    df["total_energy_mwh"] = df["electricity_mwh"] + df["gas_mwh"]
    return df


# ======================================================================================
# KPIs
# ======================================================================================
def compute_kpis(df: pd.DataFrame) -> dict:
    """Headline KPIs for a period. Final energy = electricity + natural gas (no double counting)."""
    if df.empty:
        return {"energy_mwh": 0.0, "cost_eur": 0.0, "co2_t": 0.0, "intensity_kwh_unit": np.nan, "units": 0}
    units = float(df["production_units"].sum())
    energy = float(df["total_energy_mwh"].sum())
    return {
        "energy_mwh": energy,
        "electricity_mwh": float(df["electricity_mwh"].sum()),
        "gas_mwh": float(df["gas_mwh"].sum()),
        "cost_eur": float(df["energy_cost_eur"].sum()),
        "co2_t": float(df["co2_t"].sum()),
        "units": units,
        "intensity_kwh_unit": energy * 1000 / units if units > 0 else np.nan,
        "avg_load_mw": float(df["electricity_mwh"].mean()),
        "peak_load_mw": float(df["electricity_mwh"].max()),
        "avg_price": float(df["price_eur_mwh"].mean()),
    }


def kpi_deltas(current: dict, previous: dict) -> dict:
    """Percentage change current vs previous period for each numeric KPI (None if unavailable)."""
    deltas = {}
    for key, value in current.items():
        prev = previous.get(key)
        if prev is None or not np.isfinite(prev) or prev == 0 or not np.isfinite(value):
            deltas[key] = None
        else:
            deltas[key] = (value - prev) / abs(prev) * 100
    return deltas


def previous_period(df_all: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """
    The equally long window immediately before [start, end), used for KPI deltas.
    Returns an empty frame if less than 90 % of that window is covered by data.
    """
    length = end - start
    prev = df_all[(df_all.index >= start - length) & (df_all.index < start)]
    expected_hours = length / pd.Timedelta(hours=1)
    return prev if len(prev) >= 0.9 * expected_hours else prev.iloc[0:0]


def energy_flows(df: pd.DataFrame) -> list[tuple[str, str, float]]:
    """
    Energy flows (MWh) for the Sankey diagram: carriers -> utility systems -> end use.
    Keys are i18n identifiers translated in the UI.
    """
    s = df.sum(numeric_only=True)
    flows = [
        ("electricity", "production_lines", s["el_production_lines_mwh"]),
        ("electricity", "compressed_air", s["compressed_air_mwh"]),
        ("electricity", "chillers", s["el_chillers_mwh"]),
        ("electricity", "hvac_it", s["el_hvac_it_lighting_mwh"]),
        ("gas", "paint_shop", s["gas_paint_shop_mwh"]),
        ("gas", "boilers", s["gas_boilers_mwh"]),
        ("boilers", "heating", s["gas_boilers_mwh"] * 0.92),
        ("boilers", "losses", s["gas_boilers_mwh"] * 0.08),
        ("chillers", "cooling", s["el_chillers_mwh"]),
        ("compressed_air", "pneumatics", s["compressed_air_mwh"] - s.get("heat_recovered_mwh_th", 0)),
    ]
    if s.get("heat_recovered_mwh_th", 0) > 0:
        flows.append(("compressed_air", "heating", s["heat_recovered_mwh_th"]))
    return [(a, b, float(v)) for a, b, v in flows if v > 0.01]


# ======================================================================================
# Load profile / baseload (Lastganganalyse)
# ======================================================================================
def load_profile_matrix(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Mean load per (day of week, hour of day) -> 7 x 24 matrix for the heatmap."""
    tmp = pd.DataFrame({"dow": df.index.dayofweek, "hour": df.index.hour, "value": df[column].values})
    return tmp.pivot_table(index="dow", columns="hour", values="value", aggfunc="mean").reindex(range(7))


def baseload_stats(df: pd.DataFrame, column: str) -> dict:
    """
    Grundlast (baseload) = 5th percentile of hourly load. A high non-production share means
    equipment keeps running when the factory stands still.
    """
    production = df["production_units"] > 0
    base = float(df[column].quantile(0.05))
    idle_mean = float(df.loc[~production, column].mean()) if (~production).any() else np.nan
    prod_mean = float(df.loc[production, column].mean()) if production.any() else np.nan
    idle_energy = float(df.loc[~production, column].sum())
    return {
        "baseload": base,
        "idle_mean": idle_mean,
        "production_mean": prod_mean,
        "idle_ratio": idle_mean / prod_mean if prod_mean else np.nan,
        "idle_energy": idle_energy,
        "idle_share": idle_energy / float(df[column].sum()) if df[column].sum() else np.nan,
    }


# ======================================================================================
# Anomaly detection (compressed air leak)
# ======================================================================================
def _robust_line(x: np.ndarray, y: np.ndarray, iterations: int = 10) -> tuple[float, float]:
    """Iteratively re-weighted least squares (Huber weights): a line fit that ignores outliers."""
    w = np.ones_like(y)
    slope, intercept = 0.0, float(np.median(y))
    for _ in range(iterations):
        W = np.sqrt(w)
        A = np.column_stack([x, np.ones_like(x)]) * W[:, None]
        slope, intercept = np.linalg.lstsq(A, y * W, rcond=None)[0]
        resid = y - (slope * x + intercept)
        scale = 1.4826 * np.median(np.abs(resid - np.median(resid))) or 1e-9
        k = 1.345 * scale
        w = np.where(np.abs(resid) <= k, 1.0, k / np.abs(resid))
    return float(slope), float(intercept)


def detect_anomalies(
    df: pd.DataFrame,
    column: str = "compressed_air_mwh",
    method: str = "zscore",
    threshold: float = 3.5,
    contamination: float = 0.05,
) -> pd.DataFrame:
    """
    Flag hours where a utility consumes more than its production-driven expectation.

    1. Expected load = robust linear model  load ~ production_units  (an energy signature,
       i.e. "how much compressed air should this output need?").
    2. Residual = actual - expected.
    3. method="zscore": robust Z-score of the residual (median / MAD), flag z > threshold.
       method="isolation_forest": scikit-learn IsolationForest on
       [residual, production, hour, weekend], flag outliers with a positive residual.

    Returns a frame with expected, residual, score and is_anomaly columns.
    """
    out = pd.DataFrame(index=df.index)
    x = df["production_units"].to_numpy(dtype=float)
    y = df[column].to_numpy(dtype=float)
    if len(df) < 48:
        out["expected"] = y
        out["residual"] = 0.0
        out["score"] = 0.0
        out["is_anomaly"] = False
        return out

    slope, intercept = _robust_line(x, y)
    expected = slope * x + intercept
    resid = y - expected
    med = np.median(resid)
    mad = 1.4826 * np.median(np.abs(resid - med)) or 1e-9
    z = (resid - med) / mad

    if method == "isolation_forest":
        from sklearn.ensemble import IsolationForest

        features = np.column_stack(
            [z, x / max(x.max(), 1), df.index.hour / 23, (df.index.dayofweek >= 5).astype(float)]
        )
        model = IsolationForest(n_estimators=300, contamination=contamination, random_state=7)
        labels = model.fit_predict(features)
        score = -model.score_samples(features)
        is_anom = (labels == -1) & (z > 1.5)
    else:
        score = z
        is_anom = z > threshold

    # Smooth: an hour counts if it belongs to a run of >= 3 flagged hours (leaks persist)
    flags = pd.Series(is_anom, index=df.index)
    runs = flags.groupby((flags != flags.shift()).cumsum()).transform("size")
    flags = flags & (runs >= 3)

    out["actual"] = y
    out["expected"] = expected
    out["residual"] = resid
    out["score"] = score
    out["is_anomaly"] = flags.to_numpy()
    out.attrs["model"] = {"slope": slope, "intercept": intercept, "mad": mad}
    return out


def summarize_anomalies(
    df: pd.DataFrame, anomalies: pd.DataFrame, grid_fees_eur_mwh: float = 65.0
) -> pd.DataFrame:
    """Group contiguous anomalous hours into events with wasted energy and cost."""
    flagged = anomalies["is_anomaly"]
    if not flagged.any():
        return pd.DataFrame(columns=["start", "end", "hours", "wasted_mwh", "cost_eur", "co2_t", "weekend_hours"])
    # Bridge gaps of up to 3 h so one physical leak is reported as one event
    gap = (~flagged).astype(int).groupby(flagged.cumsum()).transform("sum")
    bridged = flagged | ((~flagged) & (gap <= 3) & flagged.cummax() & flagged[::-1].cummax()[::-1])
    flagged = bridged
    group_id = (flagged != flagged.shift()).cumsum()
    events = []
    for _, idx in flagged[flagged].groupby(group_id[flagged]).groups.items():
        block = anomalies.loc[idx]
        wasted = block["residual"].clip(lower=0)
        price = df.loc[idx, "price_eur_mwh"] + grid_fees_eur_mwh
        events.append(
            {
                "start": idx.min(),
                "end": idx.max() + pd.Timedelta(hours=1),
                "hours": len(idx),
                "wasted_mwh": float(wasted.sum()),
                "cost_eur": float((wasted * price).sum()),
                "co2_t": float((wasted * df.loc[idx, "grid_co2_t_per_mwh"]).sum()),
                "weekend_hours": int((idx.dayofweek >= 5).sum()),
            }
        )
    return pd.DataFrame(events).sort_values("wasted_mwh", ascending=False).reset_index(drop=True)


# ======================================================================================
# Load-shifting optimizer (Flexibilitätsvermarktung / Lastverschiebung)
# ======================================================================================
@dataclass
class ShiftResult:
    profile: pd.DataFrame  # columns: original_mw, shifted_mw, price
    shifted_mwh: float
    cost_saving_eur: float
    co2_saving_t: float
    annual_cost_saving_eur: float
    annual_co2_saving_t: float
    peak_before_mw: float
    peak_after_mw: float
    days: float
    details: dict = field(default_factory=dict)


def optimize_load_shift(
    df: pd.DataFrame,
    flexible_share: float = 0.10,
    price_threshold: float = 150.0,
    max_shift_hours: int = 12,
    efficiency: float = 0.95,
    sink_headroom: float = 1.0,
) -> ShiftResult:
    """
    Greedy daily load shifting against day-ahead prices.

    * Source hours: hours with price > price_threshold. Up to `flexible_share` of the
      electrical load in those hours can be deferred or pre-empted (thermal storage of
      cooling/heating water, compressed-air buffer tanks, EV fleet / AGV charging).
    * Sink hours: hours with price < price_threshold within +/- `max_shift_hours`,
      cheapest first. Each sink hour can absorb up to `sink_headroom * flexible_share *
      daily mean load` extra MW (equipment capacity limit).
    * Storage losses: energy moved costs 1/efficiency in the sink hour.
    * The site's contracted peak (Leistungspreis basis) is respected: a sink hour is never
      pushed above the original maximum load of the period.

    Savings are calculated on the wholesale component (network charges are energy-based and
    unchanged, except the extra MWh caused by storage losses) and on grid CO2 intensity.
    """
    load = df["electricity_mwh"].to_numpy(dtype=float).copy()
    price = df["price_eur_mwh"].to_numpy(dtype=float)
    co2 = df["grid_co2_t_per_mwh"].to_numpy(dtype=float)
    n = len(load)
    shifted = load.copy()
    if n == 0 or flexible_share <= 0:
        return ShiftResult(
            pd.DataFrame({"original_mw": load, "shifted_mw": shifted, "price": price}, index=df.index),
            0.0, 0.0, 0.0, 0.0, 0.0, float(load.max(initial=0)), float(load.max(initial=0)), 0.0,
        )

    peak_cap = load.max()
    daily_mean = pd.Series(load, index=df.index).groupby(df.index.date).transform("mean").to_numpy()
    sink_cap = sink_headroom * flexible_share * daily_mean  # max extra MW per sink hour
    added = np.zeros(n)

    # Most expensive hours first so that the best sinks go to the biggest spreads
    for i in np.argsort(-price):
        if price[i] <= price_threshold:
            break
        movable = flexible_share * load[i]
        lo, hi = max(0, i - max_shift_hours), min(n, i + max_shift_hours + 1)
        window = np.arange(lo, hi)
        window = window[(price[window] < price_threshold) & (window != i)]
        for j in window[np.argsort(price[window])]:
            if movable <= 1e-9:
                break
            # Only worth it if the spread beats the storage losses
            if price[j] / efficiency >= price[i]:
                break
            room = min(sink_cap[j] - added[j], peak_cap - shifted[j])
            if room <= 1e-9:
                continue
            take = min(movable, room * efficiency)  # MWh delivered to the process
            shifted[i] -= take
            shifted[j] += take / efficiency
            added[j] += take / efficiency
            movable -= take

    moved_out = load - shifted
    cost_before = float((load * price).sum())
    cost_after = float((shifted * price).sum())
    # Extra MWh from storage losses also pay network charges/levies (~65 €/MWh)
    loss_mwh = float(shifted.sum() - load.sum())
    saving = cost_before - cost_after - loss_mwh * 65.0
    co2_saving = float((load * co2).sum() - (shifted * co2).sum())
    days = n / 24
    scale = 365 / days if days else 0
    profile = pd.DataFrame({"original_mw": load, "shifted_mw": shifted, "price": price}, index=df.index)
    return ShiftResult(
        profile=profile,
        shifted_mwh=float(moved_out.clip(min=0).sum()),
        cost_saving_eur=saving,
        co2_saving_t=co2_saving,
        annual_cost_saving_eur=saving * scale,
        annual_co2_saving_t=co2_saving * scale,
        peak_before_mw=float(load.max()),
        peak_after_mw=float(shifted.max()),
        days=days,
        details={"loss_mwh": loss_mwh, "source_hours": int((moved_out > 1e-6).sum())},
    )


def price_statistics(df: pd.DataFrame) -> dict:
    p = df["price_eur_mwh"]
    return {
        "mean": float(p.mean()),
        "min": float(p.min()),
        "max": float(p.max()),
        "negative_hours": int((p < 0).sum()),
        "spread_daily": float(df.groupby(df.index.date)["price_eur_mwh"].agg(lambda s: s.max() - s.min()).mean()),
        "load_weighted_price": float((p * df["electricity_mwh"]).sum() / df["electricity_mwh"].sum()),
    }


# ======================================================================================
# Measurement & Verification (IPMVP Option C, ASHRAE Guideline 14, CUSUM)
# ======================================================================================
@dataclass
class MVResult:
    daily: pd.DataFrame  # actual, predicted, savings, cusum, period
    coefficients: dict
    r2: float
    cv_rmse: float
    nmbe: float
    savings_mwh: float
    savings_pct: float
    savings_eur: float
    savings_co2_t: float
    uncertainty_pct: float
    baseline_days: int
    reporting_days: int
    go_live: pd.Timestamp


def heating_degree_days(temp_hourly: pd.Series, base: float = 16.0) -> pd.Series:
    """
    Heating degree days (Gradtagzahl-style, base 16 °C) computed from hourly temperatures:
    sum of positive (base - T_hour) / 24 per day. More accurate than daily means in the
    shoulder season, when nights need heating but afternoons do not.
    """
    return ((base - temp_hourly).clip(lower=0) / 24).resample("D").sum()


def measurement_and_verification(
    df: pd.DataFrame, go_live: pd.Timestamp, gas_price_eur_mwh: float = 42.0, hdd_base: float = 16.0
) -> MVResult:
    """
    Baseline model (fit on the period before go-live, daily resolution):

        gas_MWh/day = b0 + b1 * HDD + b2 * production_units

    Adjusted baseline = model applied to reporting-period conditions (weather + output).
    Avoided energy = adjusted baseline - actual (IPMVP "avoided energy use").
    CUSUM = running sum of (actual - predicted); a straight downward slope after go-live
    proves a persistent saving, a flat line before go-live proves the model is unbiased.
    """
    daily = pd.DataFrame(
        {
            "gas": df["gas_mwh"].resample("D").sum(),
            "temp": df["ambient_temp_c"].resample("D").mean(),
            "units": df["production_units"].resample("D").sum(),
            "hours": df["gas_mwh"].resample("D").count(),
        }
    )
    daily = daily[daily["hours"] >= 20].copy()  # drop incomplete days
    daily["hdd"] = heating_degree_days(df["ambient_temp_c"], hdd_base).reindex(daily.index)
    go_live_day = pd.Timestamp(go_live).tz_convert(TZ).normalize()
    daily["period"] = np.where(daily.index >= go_live_day, "reporting", "baseline")
    base = daily[daily["period"] == "baseline"]
    if len(base) < 7:
        raise ValueError("At least 7 baseline days are required for M&V regression")

    X = np.column_stack([np.ones(len(base)), base["hdd"], base["units"]])
    beta, *_ = np.linalg.lstsq(X, base["gas"].to_numpy(), rcond=None)
    X_all = np.column_stack([np.ones(len(daily)), daily["hdd"], daily["units"]])
    daily["predicted"] = X_all @ beta
    daily["actual"] = daily["gas"]
    daily["savings"] = daily["predicted"] - daily["actual"]
    daily["cusum"] = (daily["actual"] - daily["predicted"]).cumsum()

    # ASHRAE Guideline 14 goodness-of-fit (daily model: CV(RMSE) <= 25 %, |NMBE| <= 10 %... we
    # report against the stricter monthly criteria 15 % / 5 % as well in the UI)
    resid = base["gas"].to_numpy() - X @ beta
    n, p = len(base), X.shape[1]
    ss_res = float((resid**2).sum())
    ss_tot = float(((base["gas"] - base["gas"].mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot if ss_tot else np.nan
    mean_y = float(base["gas"].mean())
    cv_rmse = np.sqrt(ss_res / max(n - p, 1)) / mean_y * 100
    nmbe = resid.sum() / (max(n - p, 1) * mean_y) * 100

    rep = daily[daily["period"] == "reporting"]
    savings_mwh = float(rep["savings"].sum())
    predicted_rep = float(rep["predicted"].sum())
    savings_pct = savings_mwh / predicted_rep * 100 if predicted_rep else np.nan

    # ASHRAE 14 fractional savings uncertainty (simplified, 68 % confidence, no autocorrelation)
    m = max(len(rep), 1)
    if savings_pct and np.isfinite(savings_pct) and savings_pct != 0:
        uncertainty = 1.26 * (cv_rmse / 100) / (savings_pct / 100) * np.sqrt((1 + 2 / n) / m) * 100
    else:
        uncertainty = np.nan

    return MVResult(
        daily=daily,
        coefficients={"intercept": float(beta[0]), "hdd": float(beta[1]), "units": float(beta[2])},
        r2=float(r2),
        cv_rmse=float(cv_rmse),
        nmbe=float(nmbe),
        savings_mwh=savings_mwh,
        savings_pct=float(savings_pct),
        savings_eur=savings_mwh * gas_price_eur_mwh,
        savings_co2_t=savings_mwh * GAS_EMISSION_FACTOR,
        uncertainty_pct=float(uncertainty),
        baseline_days=int(len(base)),
        reporting_days=int(len(rep)),
        go_live=go_live_day,
    )
