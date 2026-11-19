"""
Data pipeline for the Gigafactory Energy & Flexibility Analytics Dashboard.

What this script does
---------------------
1. Fetches REAL German/Luxembourg (DE-LU) wholesale market data for the last N days:
   * Day-Ahead prices (EPEX SPOT auction results, EUR/MWh)
   * Renewable share of the public net electricity load (%)

   Source order (first one that works wins):
     a) Fraunhofer ISE Energy-Charts API  -> https://api.energy-charts.info
     b) Bundesnetzagentur SMARD.de API     -> https://www.smard.de/app/chart_data
     c) Offline fallback generator        -> statistically realistic synthetic market data

   The dashboard therefore never crashes, even fully offline. The source that was used
   is written to `data/metadata.json` and shown in the dashboard.

2. Simulates a realistic hourly multi-utility dataset for a large automotive/battery
   Gigafactory in Brandenburg (~45 MW average electrical load):
     Strom (electricity), Erdgas (natural gas), Druckluft (compressed air),
     Kühlwasser (cooling water), Heizwasser (heating water), production output.

   Two engineered "stories" are embedded so the analytics can find them:
     * A compressed air leak that starts on a Saturday and wastes the equivalent of
       15 % of the average compressed-air energy until it is repaired.
     * A Compressor Waste Heat Recovery project (Abwärmenutzung) that cuts natural gas
       heating demand by 18 % from its go-live date onwards (for M&V / ISO 50001).

3. Saves the merged dataset to `data/factory_energy_data.csv` (+ `data/metadata.json`).

Usage
-----
    python data/fetch_and_generate.py               # last 60 days, live APIs with fallback
    python data/fetch_and_generate.py --days 30
    python data/fetch_and_generate.py --offline     # skip the APIs (synthetic market data)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import requests
except ImportError:  # requests is in requirements.txt, but keep offline mode usable without it
    requests = None

# --------------------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------------------
TZ = "Europe/Berlin"
DATA_DIR = Path(__file__).resolve().parent
OUTPUT_CSV = DATA_DIR / "factory_energy_data.csv"
METADATA_JSON = DATA_DIR / "metadata.json"

ENERGY_CHARTS_BASE = "https://api.energy-charts.info"
SMARD_BASE = "https://www.smard.de/app/chart_data"
HTTP_TIMEOUT_S = 30
HTTP_RETRIES = 3
USER_AGENT = "gigafactory-energy-dashboard/1.0 (portfolio project; python-requests)"

# SMARD filter ids (see smard.de "Downloadcenter" / API docs)
SMARD_PRICE_FILTER = 4169  # Marktpreis Deutschland/Luxemburg (Day-Ahead)
SMARD_RENEWABLE_FILTERS = {
    1225: "Wind Offshore",
    4067: "Wind Onshore",
    4068: "Photovoltaik",
    4066: "Biomasse",
    1226: "Wasserkraft",
    1228: "Sonstige Erneuerbare",
}
SMARD_LOAD_FILTER = 410  # Stromverbrauch: Gesamt (Netzlast)

# Engineering constants for the synthetic factory
UNITS_PER_HOUR_WEEKDAY = 32.0  # vehicles per hour in 3-shift operation (~3,800 vehicles/week)
GAS_EMISSION_FACTOR_T_PER_MWH = 0.201  # UBA factor for natural gas (t CO2 / MWh_Hs, rounded)
HEAT_RECOVERY_REDUCTION = 0.18  # 18 % lower gas heating demand after go-live
LEAK_SHARE_OF_AVG_AIR = 0.15  # leak = 15 % of the average compressed-air energy

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
log = logging.getLogger("pipeline")


@dataclass
class MarketData:
    """Hourly DE-LU market data plus a description of where it came from."""

    frame: pd.DataFrame  # index: hourly tz-aware (Europe/Berlin); cols: price_eur_mwh, renewable_share_pct
    price_source: str
    renewable_source: str


# --------------------------------------------------------------------------------------
# HTTP helper
# --------------------------------------------------------------------------------------
def _get_json(url: str, params: dict | None = None) -> dict:
    """GET a JSON document with retries and exponential backoff (handles HTTP 429)."""
    if requests is None:
        raise RuntimeError("The 'requests' package is not installed")
    last_error: Exception | None = None
    for attempt in range(1, HTTP_RETRIES + 1):
        try:
            response = requests.get(
                url, params=params, timeout=HTTP_TIMEOUT_S, headers={"User-Agent": USER_AGENT}
            )
            if response.status_code == 429:
                wait = int(response.headers.get("Retry-After", 2**attempt))
                log.warning("Rate limited by %s, waiting %ss", url, wait)
                time.sleep(min(wait, 30))
                continue
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # network errors, JSON errors, HTTP errors
            last_error = exc
            log.warning("Attempt %d/%d for %s failed: %s", attempt, HTTP_RETRIES, url, exc)
            if attempt < HTTP_RETRIES:
                time.sleep(2**attempt * 0.5)
    raise RuntimeError(f"Request failed after {HTTP_RETRIES} attempts: {url}") from last_error


def _to_hourly(series: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
    """Resample a (possibly 15-minute) tz-aware series to the hourly target index."""
    series = series.sort_index()
    series = series[~series.index.duplicated(keep="first")]
    hourly = series.resample("h").mean()
    return hourly.reindex(index).interpolate(limit=6).ffill().bfill()


# --------------------------------------------------------------------------------------
# Source A: Fraunhofer ISE Energy-Charts
# --------------------------------------------------------------------------------------
def fetch_energy_charts_prices(start: datetime, end: datetime, index: pd.DatetimeIndex) -> pd.Series:
    """Day-Ahead prices for bidding zone DE-LU (15-min resolution since Oct 2025)."""
    payload = _get_json(
        f"{ENERGY_CHARTS_BASE}/price",
        params={"bzn": "DE-LU", "start": start.strftime("%Y-%m-%d"), "end": end.strftime("%Y-%m-%d")},
    )
    seconds, prices = payload.get("unix_seconds") or [], payload.get("price") or []
    if not seconds or len(seconds) != len(prices):
        raise ValueError("Energy-Charts price payload is empty or malformed")
    ts = pd.to_datetime(seconds, unit="s", utc=True).tz_convert(TZ)
    series = pd.Series(pd.to_numeric(prices, errors="coerce"), index=ts, dtype="float64").dropna()
    if series.empty:
        raise ValueError("Energy-Charts returned no valid prices")
    return _to_hourly(series, index)


def fetch_energy_charts_renewable_share(
    start: datetime, end: datetime, index: pd.DatetimeIndex
) -> pd.Series:
    """Renewable share of public net load in Germany (%), from the public power endpoint."""
    payload = _get_json(
        f"{ENERGY_CHARTS_BASE}/public_power",
        params={"country": "de", "start": start.strftime("%Y-%m-%d"), "end": end.strftime("%Y-%m-%d")},
    )
    seconds = payload.get("unix_seconds") or []
    types = {p.get("name", ""): p.get("data") for p in payload.get("production_types", [])}
    if not seconds or not types:
        raise ValueError("Energy-Charts public_power payload is empty or malformed")
    ts = pd.to_datetime(seconds, unit="s", utc=True).tz_convert(TZ)

    def as_series(values) -> pd.Series:
        return pd.Series(pd.to_numeric(pd.Series(values), errors="coerce").values, index=ts)

    # Preferred: the share series Energy-Charts publishes directly
    for wanted in ("renewable share of load", "renewable share of generation"):
        for name, values in types.items():
            if name.lower() == wanted and values:
                share = as_series(values).dropna()
                if not share.empty:
                    return _to_hourly(share.clip(0, 100), index)

    # Otherwise compute it: sum of renewable generation / load
    renewable_keywords = ("wind", "solar", "biomass", "hydro", "geothermal", "renewable")
    renewable = None
    for name, values in types.items():
        lname = name.lower()
        excluded = "share" in lname or "pumped" in lname  # pumped storage is not renewable
        if any(k in lname for k in renewable_keywords) and not excluded and values:
            part = as_series(values).fillna(0).clip(lower=0)
            renewable = part if renewable is None else renewable + part
    load_name = next((n for n in types if n.lower() == "load"), None)
    if renewable is None or load_name is None:
        raise ValueError("Could not derive renewable share from Energy-Charts data")
    load = as_series(types[load_name]).replace(0, np.nan)
    share = (renewable / load * 100).clip(0, 100).dropna()
    return _to_hourly(share, index)


# --------------------------------------------------------------------------------------
# Source B: SMARD.de (Bundesnetzagentur)
# --------------------------------------------------------------------------------------
def _fetch_smard_series(filter_id: int, region: str, start: datetime, end: datetime) -> pd.Series:
    """SMARD stores hourly data in weekly JSON chunks; download every chunk we need."""
    index_doc = _get_json(f"{SMARD_BASE}/{filter_id}/{region}/index_hour.json")
    chunk_starts = sorted(index_doc.get("timestamps", []))
    if not chunk_starts:
        raise ValueError(f"SMARD index for filter {filter_id} is empty")
    start_ms = int(pd.Timestamp(start).timestamp() * 1000) - 7 * 24 * 3600 * 1000
    end_ms = int(pd.Timestamp(end).timestamp() * 1000)
    wanted = [t for t in chunk_starts if start_ms <= t <= end_ms]
    points: list[list] = []
    for chunk in wanted:
        doc = _get_json(f"{SMARD_BASE}/{filter_id}/{region}/{filter_id}_{region}_hour_{chunk}.json")
        points.extend(p for p in doc.get("series", []) if p and p[1] is not None)
    if not points:
        raise ValueError(f"SMARD returned no data for filter {filter_id}")
    ts = pd.to_datetime([p[0] for p in points], unit="ms", utc=True).tz_convert(TZ)
    return pd.Series([float(p[1]) for p in points], index=ts)


def fetch_smard_prices(start: datetime, end: datetime, index: pd.DatetimeIndex) -> pd.Series:
    return _to_hourly(_fetch_smard_series(SMARD_PRICE_FILTER, "DE-LU", start, end), index)


def fetch_smard_renewable_share(start: datetime, end: datetime, index: pd.DatetimeIndex) -> pd.Series:
    renewable = None
    for filter_id in SMARD_RENEWABLE_FILTERS:
        part = _to_hourly(_fetch_smard_series(filter_id, "DE", start, end), index).clip(lower=0)
        renewable = part if renewable is None else renewable + part
    load = _to_hourly(_fetch_smard_series(SMARD_LOAD_FILTER, "DE", start, end), index)
    return (renewable / load.replace(0, np.nan) * 100).clip(0, 100).ffill().bfill()


# --------------------------------------------------------------------------------------
# Source C: offline fallback generator
# --------------------------------------------------------------------------------------
def generate_synthetic_market(index: pd.DatetimeIndex, rng: np.random.Generator) -> pd.DataFrame:
    """
    Realistic DE-LU autumn market: wind follows a slowly varying weather regime, solar a
    daylight bell curve, and the price follows the residual load (merit-order effect).
    High renewable hours produce very low or negative prices, as in the real market.
    """
    n = len(index)
    hour = index.hour.to_numpy()
    doy = index.dayofyear.to_numpy()

    # Wind: AR(1) weather regime with multi-day persistence
    wind = np.empty(n)
    wind[0] = 0.35
    for i in range(1, n):
        wind[i] = 0.35 + 0.985 * (wind[i - 1] - 0.35) + rng.normal(0, 0.035)
    wind = np.clip(wind, 0.03, 0.85)

    # Solar: daylight window shrinks towards winter
    daylight = np.clip(np.cos((doy - 172) / 365 * 2 * np.pi) * 0.5 + 0.5, 0.15, 1.0)
    solar_shape = np.clip(np.sin((hour - 6) / 12 * np.pi), 0, None) ** 1.5
    solar = solar_shape * daylight * 0.45 * rng.uniform(0.4, 1.0, n)

    other_renewables = 0.10  # biomass + hydro
    renewable_share = np.clip((wind * 0.8 + solar + other_renewables) * 100, 5, 100)

    # Price via residual load: weekday peaks, cheaper weekends and nights
    weekday = index.dayofweek.to_numpy() < 5
    demand_shape = (
        0.75
        + 0.15 * np.exp(-((hour - 8) ** 2) / 6)
        + 0.22 * np.exp(-((hour - 18) ** 2) / 5)
        - 0.12 * (hour < 5)
    ) * np.where(weekday, 1.0, 0.86)
    residual = demand_shape - renewable_share / 100
    price = 92 + 230 * residual + rng.normal(0, 9, n)
    price = np.where(renewable_share > 80, price - rng.uniform(20, 70, n), price)
    price = np.clip(price, -80, 450)

    return pd.DataFrame(
        {"price_eur_mwh": price.round(2), "renewable_share_pct": renewable_share.round(1)}, index=index
    )


def load_market_data(index: pd.DatetimeIndex, offline: bool, rng: np.random.Generator) -> MarketData:
    """Try Energy-Charts, then SMARD, then the synthetic generator, independently per signal."""
    synthetic = generate_synthetic_market(index, rng)
    start, end = index[0].to_pydatetime(), index[-1].to_pydatetime()
    if offline:
        log.info("Offline mode: using synthetic market data")
        return MarketData(synthetic, "Synthetic fallback (offline mode)", "Synthetic fallback (offline mode)")

    def first_working(fetchers):
        for label, fn in fetchers:
            try:
                series = fn(start, end, index)
                coverage = series.notna().mean()
                if coverage < 0.9:
                    raise ValueError(f"only {coverage:.0%} coverage")
                log.info("%s: OK (%d hourly values)", label, series.notna().sum())
                return series, label
            except Exception as exc:
                log.warning("%s failed: %s", label, exc)
        return None, None

    price, price_src = first_working(
        [
            ("Fraunhofer ISE Energy-Charts (DE-LU Day-Ahead)", fetch_energy_charts_prices),
            ("SMARD.de / Bundesnetzagentur (DE-LU Day-Ahead)", fetch_smard_prices),
        ]
    )
    share, share_src = first_working(
        [
            ("Fraunhofer ISE Energy-Charts (public power)", fetch_energy_charts_renewable_share),
            ("SMARD.de / Bundesnetzagentur (generation & load)", fetch_smard_renewable_share),
        ]
    )
    frame = synthetic.copy()
    if price is not None:
        frame["price_eur_mwh"] = price.round(2)
    if share is not None:
        frame["renewable_share_pct"] = share.round(1)
    return MarketData(
        frame,
        price_src or "Synthetic fallback (APIs unreachable)",
        share_src or "Synthetic fallback (APIs unreachable)",
    )


# --------------------------------------------------------------------------------------
# Synthetic Gigafactory simulation
# --------------------------------------------------------------------------------------
def simulate_ambient_temperature(index: pd.DatetimeIndex, rng: np.random.Generator) -> np.ndarray:
    """Brandenburg climate: seasonal sine, diurnal cycle and multi-day weather fronts (°C)."""
    doy = index.dayofyear.to_numpy() + index.hour.to_numpy() / 24
    hour = index.hour.to_numpy()
    seasonal = 9.8 - 9.8 * np.cos((doy - 20) / 365 * 2 * np.pi)  # ~0 °C Jan, ~19.6 °C Jul
    diurnal = 3.5 * np.sin((hour - 9) / 24 * 2 * np.pi)
    front = np.empty(len(index))
    front[0] = 0.0
    for i in range(1, len(index)):
        front[i] = 0.99 * front[i - 1] + rng.normal(0, 0.35)
    return seasonal + diurnal + front


def simulate_production(index: pd.DatetimeIndex, rng: np.random.Generator) -> np.ndarray:
    """
    Hourly vehicle output.
    Mon-Fri: 3 shifts (06-14, 14-22, 22-06) with dips at shift handovers.
    Saturday: one early shift. Sunday: no production (maintenance only).
    """
    hour = index.hour.to_numpy()
    dow = index.dayofweek.to_numpy()
    units = np.full(len(index), UNITS_PER_HOUR_WEEKDAY)
    units = np.where(np.isin(hour, [6, 14, 22]), units * 0.55, units)  # shift handover
    units = np.where((hour >= 22) | (hour < 6), units * 0.92, units)  # night shift slightly slower
    units = units * rng.normal(1.0, 0.05, len(index))
    # Monday 00:00-06:00 still belongs to the weekend standstill (ramp-up at 06:00)
    units = np.where((dow == 0) & (hour < 6), 0.0, units)
    saturday = dow == 5
    units = np.where(saturday & (hour >= 6) & (hour < 14), units * 0.6, np.where(saturday, 0.0, units))
    units = np.where(dow == 6, 0.0, units)
    # The Friday night shift ends at 06:00 Saturday -> Saturday 00-06 keeps producing
    units = np.where(saturday & (hour < 6), UNITS_PER_HOUR_WEEKDAY * 0.92 * rng.normal(1, 0.05, len(index)), units)
    return np.clip(units, 0, None).round(0)


def simulate_factory(index: pd.DatetimeIndex, rng: np.random.Generator) -> tuple[pd.DataFrame, dict]:
    """Physics-inspired hourly multi-utility model. All energy values are MWh per hour (= MW)."""
    n = len(index)
    temp = simulate_ambient_temperature(index, rng)
    units = simulate_production(index, rng)
    producing = units > 0
    noise = lambda sd: rng.normal(1.0, sd, n)  # noqa: E731 - small helper

    # ---- Druckluft / compressed air (electricity used by the compressor station) ----------
    # Proportional to pneumatic tools & robots + a constant system leakage baseline
    air_base = 1.70 + 0.105 * units
    air_el = air_base * noise(0.02)
    avg_air = float(air_el.mean())

    # Engineered anomaly: leak starts on a Saturday morning, repaired the following Tuesday
    saturdays = index[(index.dayofweek == 5) & (index.hour == 8)]
    leak_start = saturdays[min(5, len(saturdays) - 1)] if len(saturdays) else index[n // 2]
    leak_end = (leak_start + pd.Timedelta(days=3)).replace(hour=10)  # Tuesday 10:00
    leak_mask = (index >= leak_start) & (index < leak_end)
    leak_mw = LEAK_SHARE_OF_AVG_AIR * avg_air
    air_leak = np.where(leak_mask, leak_mw * noise(0.03), 0.0)
    air_el = air_el + air_leak
    air_volume_nm3 = air_el * 1000 / 0.11  # specific power ~0.11 kWh/Nm³ at 7 bar

    # ---- Kühlwasser / cooling water (thermal energy removed by chillers) -------------------
    cooling_th = (5.5 + 0.30 * units + 0.45 * np.clip(temp - 8, 0, None)) * noise(0.03)
    cop = np.clip(7.5 - 0.18 * temp, 4.0, 7.0)  # free cooling assist in cold weather
    chiller_el = cooling_th / cop

    # ---- Heizwasser / heating water (space heating + pretreatment & e-coat baths) -----------
    hdd = np.clip(16 - temp, 0, None)  # heating degree driver
    occupancy = np.where(producing, 1.0, 0.7)
    heating_th = (3.5 + 0.06 * units + 1.05 * hdd * occupancy) * noise(0.03)

    # ---- Erdgas / natural gas -----------------------------------------------------------------
    # Boilers supply heating water (efficiency 92 %), paint shop ovens burn gas directly.
    paint_gas = np.where(producing, 2.2 + 0.17 * units, 1.6) * noise(0.03)  # ovens on standby
    boiler_gas_baseline = heating_th / 0.92
    go_live = (index[0] + pd.Timedelta(days=int(len(np.unique(index.date)) * 0.45))).normalize()
    while go_live.dayofweek != 0:  # projects go live on a Monday
        go_live += pd.Timedelta(days=1)
    post = index >= go_live
    gas_baseline = paint_gas + boiler_gas_baseline
    # Compressor waste heat now pre-heats the heating water loop. The recovered heat displaces
    # boiler gas, so total gas heating demand falls by 18 % (≈75 % of compressor input power).
    gas_saved = np.where(post, gas_baseline * HEAT_RECOVERY_REDUCTION, 0.0)
    boiler_gas = boiler_gas_baseline - gas_saved
    gas = paint_gas + boiler_gas
    recovered_heat_th = gas_saved * 0.92

    # ---- Strom / electricity -----------------------------------------------------------------
    production_el = (11.0 + 0.95 * units) * noise(0.025)  # body shop, GA, cell/battery lines
    shift_lighting = np.where(producing, 2.8, 1.2)
    hvac_it_el = (2.5 + shift_lighting + 0.12 * np.clip(temp - 18, 0, None)) * noise(0.02)
    electricity = production_el + air_el + chiller_el + hvac_it_el

    frame = pd.DataFrame(
        {
            "ambient_temp_c": temp.round(2),
            "production_units": units.astype(int),
            "electricity_mwh": electricity.round(4),
            "el_production_lines_mwh": production_el.round(4),
            "el_hvac_it_lighting_mwh": hvac_it_el.round(4),
            "el_chillers_mwh": chiller_el.round(4),
            "compressed_air_mwh": air_el.round(4),
            "compressed_air_nm3": air_volume_nm3.round(0),
            "gas_mwh": gas.round(4),
            "gas_paint_shop_mwh": paint_gas.round(4),
            "gas_boilers_mwh": boiler_gas.round(4),
            "cooling_water_mwh_th": cooling_th.round(4),
            "heating_water_mwh_th": heating_th.round(4),
            "heat_recovered_mwh_th": recovered_heat_th.round(4),
            "leak_injected": leak_mask,
            "post_heat_recovery": post,
        },
        index=index,
    )
    events = {
        "leak_start": leak_start.isoformat(),
        "leak_end": leak_end.isoformat(),
        "leak_mw": round(leak_mw, 3),
        "heat_recovery_go_live": go_live.isoformat(),
        "heat_recovery_reduction": HEAT_RECOVERY_REDUCTION,
    }
    return frame, events


# --------------------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------------------
def build_dataset(days: int, offline: bool, seed: int) -> tuple[pd.DataFrame, dict]:
    rng = np.random.default_rng(seed)
    today = pd.Timestamp.now(tz=TZ).normalize()
    start = today - pd.Timedelta(days=days)
    index = pd.date_range(start, today - pd.Timedelta(hours=1), freq="h", tz=TZ, name="timestamp")
    log.info("Building %d hourly records from %s to %s", len(index), index[0], index[-1])

    market = load_market_data(index, offline, rng)
    factory, events = simulate_factory(index, rng)
    data = factory.join(market.frame)

    # Hourly grid CO2 intensity estimate from the renewable share (t CO2 / MWh_el).
    # Fossil mix in DE ~0.82 t/MWh; renewables ~0.02 t/MWh (life-cycle, rounded).
    ren = data["renewable_share_pct"] / 100
    data["grid_co2_t_per_mwh"] = (0.82 * (1 - ren) + 0.02 * ren).round(4)

    metadata = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "start": index[0].isoformat(),
        "end": index[-1].isoformat(),
        "records": int(len(data)),
        "price_source": market.price_source,
        "renewable_source": market.renewable_source,
        "gas_emission_factor_t_per_mwh": GAS_EMISSION_FACTOR_T_PER_MWH,
        "events": events,
        "seed": seed,
    }
    return data, metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=60, help="history length in days (30-90 recommended)")
    parser.add_argument("--offline", action="store_true", help="do not call any API")
    parser.add_argument("--seed", type=int, default=42, help="random seed for the factory simulation")
    parser.add_argument(
        "--quick", action="store_true", help="short timeouts and a single attempt per request (used by the app)"
    )
    args = parser.parse_args(argv)

    if args.quick:
        global HTTP_TIMEOUT_S, HTTP_RETRIES
        HTTP_TIMEOUT_S, HTTP_RETRIES = 10, 1

    if not 7 <= args.days <= 365:
        parser.error("--days must be between 7 and 365")

    data, metadata = build_dataset(args.days, args.offline, args.seed)
    out = data.reset_index()
    out["timestamp"] = out["timestamp"].map(lambda t: t.isoformat())
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUTPUT_CSV, index=False)
    METADATA_JSON.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    log.info("Price data: %s", metadata["price_source"])
    log.info("Renewable share: %s", metadata["renewable_source"])
    log.info(
        "Saved %s (%d rows, avg load %.1f MW, %.0f vehicles)",
        OUTPUT_CSV.relative_to(DATA_DIR.parent),
        len(out),
        data["electricity_mwh"].mean(),
        data["production_units"].sum(),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
