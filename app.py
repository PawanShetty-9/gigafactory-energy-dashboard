"""
Gigafactory Energy & Flexibility Analytics Dashboard
====================================================

Streamlit app with four views:
  1. Executive overview & multi-utility KPIs        (Gesamtübersicht)
  2. Load profile analysis & compressed-air leaks   (Lastganganalyse & Leckagen)
  3. DE day-ahead market & load-shifting simulator  (Strommarkt & Flexibilität)
  4. Project M&V for ISO 50001 / EMAS               (Projektvalidierung)

Run:  streamlit run app.py
"""

from __future__ import annotations

import os
from datetime import timedelta

import numpy as np
import pandas as pd
import streamlit as st

from utils import analytics as an
from utils import charts as ch
from utils.i18n import t

st.set_page_config(
    page_title="Gigafactory Energy & Flexibility Analytics",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Small visual polish that works in light and dark mode
st.markdown(
    """
    <style>
      .block-container {padding-top: 1.6rem; padding-bottom: 2rem;}
      div[data-testid="stMetric"] {
          border: 1px solid rgba(128,128,128,0.25);
          border-radius: 12px;
          padding: 14px 16px 10px 16px;
          background: rgba(128,128,128,0.06);
      }
      div[data-testid="stMetricLabel"] p {font-size: 0.85rem; opacity: 0.85;}
      .source-note {font-size: 0.78rem; opacity: 0.75; line-height: 1.35;}
      .insight {border-left: 4px solid #10B981; padding: 0.5rem 0.9rem; border-radius: 4px;
                background: rgba(16,185,129,0.08); margin: 0.4rem 0 0.8rem 0;}
    </style>
    """,
    unsafe_allow_html=True,
)


# ======================================================================================
# Cached data access
# ======================================================================================
def _dataset_version() -> float:
    """Cache key: changes whenever the CSV is regenerated."""
    return an.DATA_CSV.stat().st_mtime if an.DATA_CSV.exists() else 0.0


@st.cache_data(show_spinner=False)
def load_base(version: float) -> pd.DataFrame:
    return an.load_dataset()


@st.cache_data(show_spinner=False)
def load_meta(version: float) -> dict:
    return an.load_metadata()


@st.cache_data(show_spinner=False)
def with_costs(df: pd.DataFrame, grid_fees: float, gas_price: float) -> pd.DataFrame:
    return an.add_cost_columns(df, grid_fees, gas_price)


@st.cache_data(show_spinner=False)
def cached_anomalies(df: pd.DataFrame, method: str, threshold: float, contamination: float) -> pd.DataFrame:
    return an.detect_anomalies(df, method=method, threshold=threshold, contamination=contamination)


@st.cache_data(show_spinner=False)
def cached_shift(df: pd.DataFrame, share: float, threshold: float, window: int, eff: float):
    return an.optimize_load_shift(df, share, threshold, window, eff)


@st.cache_data(show_spinner=False)
def cached_mv(df: pd.DataFrame, go_live: pd.Timestamp, gas_price: float):
    return an.measurement_and_verification(df, go_live, gas_price)


def rebuild_dataset(offline: bool = False) -> tuple[bool, str]:
    """Run the data pipeline in-process (used for the first start and the refresh button)."""
    try:
        from data import fetch_and_generate as pipeline

        args = ["--days", "60", "--quick"] + (["--offline"] if offline else [])
        pipeline.main(args)
        st.cache_data.clear()
        return True, ""
    except Exception as exc:  # surface the error in the UI instead of crashing
        return False, str(exc)


# ======================================================================================
# Formatting helpers
# ======================================================================================
def fmt_num(value: float, decimals: int = 0, lang: str = "en") -> str:
    if value is None or not np.isfinite(value):
        return "–"
    text = f"{value:,.{decimals}f}"
    if lang == "de":  # German number format: 1.234,5
        text = text.replace(",", "§").replace(".", ",").replace("§", ".")
    return text


def fmt_delta(delta: float | None, lang: str) -> str | None:
    if delta is None or not np.isfinite(delta):
        return None
    return f"{fmt_num(delta, 1, lang)} % {t('vs_prev', lang)}"


def fmt_eur(value: float, lang: str) -> str:
    if abs(value) >= 1e6:
        return f"€ {fmt_num(value / 1e6, 2, lang)} M" if lang == "en" else f"{fmt_num(value / 1e6, 2, lang)} Mio. €"
    if abs(value) >= 1e3:
        return f"€ {fmt_num(value / 1e3, 1, lang)} k" if lang == "en" else f"{fmt_num(value / 1e3, 1, lang)} Tsd. €"
    return f"€ {fmt_num(value, 0, lang)}" if lang == "en" else f"{fmt_num(value, 0, lang)} €"


def show_chart(fig) -> None:
    st.plotly_chart(fig, width="stretch", theme="streamlit", config={"displaylogo": False})


# ======================================================================================
# Sidebar
# ======================================================================================
with st.sidebar:
    lang_label = st.radio("🌐 Language / Sprache", ["English", "Deutsch"], horizontal=True)
    lang = "de" if lang_label == "Deutsch" else "en"

if not an.DATA_CSV.exists():
    with st.spinner(t("missing_data", lang)):
        ok, err = rebuild_dataset(offline=False)
    if not ok:
        st.error(f"{t('refresh_fail', lang)}: {err}")
        st.stop()



@st.cache_resource(show_spinner=False)
def auto_refresh_once() -> tuple[bool, str]:
    """
    Once per server process (e.g. each Streamlit Community Cloud boot): if the bundled dataset
    uses synthetic market data or is more than 3 days old, try to pull real DE-LU data.
    Set GIGAFACTORY_AUTO_REFRESH=0 to disable.
    """
    if os.environ.get("GIGAFACTORY_AUTO_REFRESH", "1") == "0":
        return False, "disabled"
    meta_now = an.load_metadata()
    synthetic = str(meta_now.get("price_source", "Synthetic")).startswith("Synthetic")
    try:
        age_days = (pd.Timestamp.now(tz=an.TZ) - pd.Timestamp(meta_now["end"])).days
    except (KeyError, ValueError, TypeError):
        age_days = 999
    if not synthetic and age_days <= 3:
        return False, "fresh"
    return rebuild_dataset(offline=False)


if an.DATA_CSV.exists():
    with st.spinner("Energy-Charts / SMARD …"):
        auto_refresh_once()

version = _dataset_version()
base_df = load_base(version)
meta = load_meta(version)

with st.sidebar:
    min_day = base_df.index.min().date()
    max_day = base_df.index.max().date()
    period = st.date_input(
        f"📅 {t('period', lang)}",
        value=(min_day, max_day),
        min_value=min_day,
        max_value=max_day,
        format="DD.MM.YYYY" if lang == "de" else "YYYY/MM/DD",
    )
    if isinstance(period, (tuple, list)):
        start_day = period[0]
        end_day = period[1] if len(period) > 1 else period[0]
    else:
        start_day = end_day = period

    st.markdown(f"**💶 {t('settings', lang)}**")
    grid_fees = st.slider(t("grid_fees", lang), 20, 140, 65, 5, help=t("grid_fees_help", lang))
    gas_price = st.slider(t("gas_price", lang), 20, 90, 42, 1)

    st.divider()
    st.markdown(f"**🛰️ {t('data_source', lang)}**")
    st.markdown(
        f"""<div class="source-note">
        <b>{t('price_source', lang)}:</b> {meta.get('price_source', '–')}<br>
        <b>{t('ren_source', lang)}:</b> {meta.get('renewable_source', '–')}<br>
        <b>{t('factory_source', lang)}:</b> {t('factory_source_val', lang)}<br>
        <b>{t('generated', lang)}:</b> {str(meta.get('generated_at', '–'))[:16].replace('T', ' ')}
        </div>""",
        unsafe_allow_html=True,
    )
    if st.button(f"🔄 {t('refresh', lang)}", width="stretch"):
        with st.spinner("Energy-Charts / SMARD …"):
            ok, err = rebuild_dataset(offline=False)
        if ok:
            st.success(t("refresh_ok", lang))
            st.rerun()
        else:
            st.error(f"{t('refresh_fail', lang)}: {err}")

# Apply tariff assumptions and the date filter
df_all = with_costs(base_df, float(grid_fees), float(gas_price))
start_ts = pd.Timestamp(start_day, tz=an.TZ)
end_ts = pd.Timestamp(end_day + timedelta(days=1), tz=an.TZ)
df = df_all[(df_all.index >= start_ts) & (df_all.index < end_ts)]

# ======================================================================================
# Header
# ======================================================================================
st.title(f"⚡ {t('title', lang)}")
st.caption(t("subtitle", lang))

if df.empty:
    st.warning(t("no_data", lang))
    st.stop()

tab1, tab2, tab3, tab4 = st.tabs([t("tab1", lang), t("tab2", lang), t("tab3", lang), t("tab4", lang)])

# ======================================================================================
# Tab 1 — Executive overview
# ======================================================================================
with tab1:
    kpis = an.compute_kpis(df)
    prev = an.previous_period(df_all, start_ts, end_ts)
    deltas = an.kpi_deltas(kpis, an.compute_kpis(prev)) if not prev.empty else {}

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        t("kpi_energy", lang),
        f"{fmt_num(kpis['energy_mwh'], 0, lang)} MWh",
        fmt_delta(deltas.get("energy_mwh"), lang),
        delta_color="inverse",
    )
    c2.metric(
        t("kpi_cost", lang), fmt_eur(kpis["cost_eur"], lang), fmt_delta(deltas.get("cost_eur"), lang), delta_color="inverse"
    )
    c3.metric(
        t("kpi_co2", lang),
        f"{fmt_num(kpis['co2_t'], 0, lang)} t",
        fmt_delta(deltas.get("co2_t"), lang),
        delta_color="inverse",
    )
    c4.metric(
        t("kpi_intensity", lang) + (" (kWh/Fzg.)" if lang == "de" else " (kWh/vehicle)"),
        f"{fmt_num(kpis['intensity_kwh_unit'], 0, lang)} kWh",
        fmt_delta(deltas.get("intensity_kwh_unit"), lang),
        delta_color="inverse",
    )
    c5, c6, c7, c8 = st.columns(4)
    c5.metric(t("kpi_units", lang), fmt_num(kpis["units"], 0, lang), fmt_delta(deltas.get("units"), lang))
    c6.metric(t("kpi_avg_load", lang), f"{fmt_num(kpis['avg_load_mw'], 1, lang)} MW")
    c7.metric(t("kpi_peak", lang), f"{fmt_num(kpis['peak_load_mw'], 1, lang)} MW")
    weighted = (df["price_eur_mwh"] * df["electricity_mwh"]).sum() / df["electricity_mwh"].sum()
    c8.metric(t("kpi_price", lang), f"{fmt_num(weighted, 1, lang)} €/MWh")

    head_l, head_r = st.columns([3, 1])
    head_l.subheader(t("t1_trend", lang))
    resolution = head_r.radio(
        t("t1_resolution", lang), ["daily", "hourly"], format_func=lambda k: t(k, lang), horizontal=True
    )
    show_chart(ch.utility_trend(df, lang, resolution))
    st.caption(t("t1_trend_note", lang))

    left, right = st.columns([3, 2])
    with left:
        st.subheader(t("t1_sankey", lang))
        show_chart(ch.energy_sankey(an.energy_flows(df), lang))
    with right:
        st.subheader(t("t1_mix", lang))
        show_chart(ch.cost_co2_split(df, lang))
        st.subheader(t("t1_intensity", lang))
        show_chart(ch.intensity_chart(df, lang))

# ======================================================================================
# Tab 2 — Load profile & leak detection
# ======================================================================================
with tab2:
    utility_options = {
        "compressed_air": "compressed_air_mwh",
        "electricity": "electricity_mwh",
        "gas": "gas_mwh",
        "cooling": "cooling_water_mwh_th",
        "heating": "heating_water_mwh_th",
    }
    st.subheader(t("t2_heatmap", lang))
    sel = st.selectbox(t("t2_utility", lang), list(utility_options), format_func=lambda k: t(k, lang))
    col = utility_options[sel]
    show_chart(ch.load_heatmap(an.load_profile_matrix(df, col), lang))

    stats = an.baseload_stats(df, col)
    b1, b2, b3 = st.columns(3)
    b1.metric(t("t2_baseload", lang), f"{fmt_num(stats['baseload'], 2, lang)} MW")
    b2.metric(t("t2_idle_ratio", lang), f"{fmt_num(stats['idle_ratio'] * 100, 0, lang)} %")
    b3.metric(
        t("t2_idle_share", lang),
        f"{fmt_num(stats['idle_energy'], 0, lang)} MWh",
        f"{fmt_num(stats['idle_share'] * 100, 1, lang)} %",
        delta_color="off", delta_arrow="off",
    )

    st.divider()
    st.subheader(t("t2_detection", lang))
    st.markdown(f"<div class='insight'>{t('t2_explain', lang)}</div>", unsafe_allow_html=True)
    m1, m2 = st.columns([2, 2])
    method = m1.radio(
        t("t2_method", lang),
        ["zscore", "isolation_forest"],
        format_func=lambda k: t("t2_zscore" if k == "zscore" else "t2_iforest", lang),
        horizontal=True,
    )
    if method == "zscore":
        threshold = m2.slider(t("t2_threshold", lang), 2.0, 6.0, 3.5, 0.5)
        contamination = 0.05
    else:
        contamination = m2.slider(t("t2_contamination", lang), 0.01, 0.15, 0.05, 0.01)
        threshold = 3.5

    anomalies = cached_anomalies(df, method, threshold, contamination)
    events = an.summarize_anomalies(df, anomalies, float(grid_fees))
    show_chart(ch.anomaly_chart(anomalies, lang))

    wasted = float(events["wasted_mwh"].sum()) if not events.empty else 0.0
    wasted_cost = float(events["cost_eur"].sum()) if not events.empty else 0.0
    leak_hours = int(events["hours"].sum()) if not events.empty else 0
    w1, w2, w3 = st.columns(3)
    w1.metric(t("t2_wasted", lang), f"{fmt_num(wasted, 1, lang)} MWh", f"{leak_hours} h", delta_color="off", delta_arrow="off")
    w2.metric(t("t2_wasted_cost", lang), fmt_eur(wasted_cost, lang))
    # A leak that is never found wastes its flow rate every hour of the year
    leak_rate_mw = wasted / leak_hours if leak_hours else 0.0
    w3.metric(
        t("t2_annual", lang),
        fmt_eur(leak_rate_mw * 8760 * (df["price_eur_mwh"].mean() + grid_fees), lang),
        f"{fmt_num(leak_rate_mw * 8760, 0, lang)} MWh/a",
        delta_color="off", delta_arrow="off",
    )

    st.markdown(f"**{t('t2_events', lang)}**")
    if events.empty:
        st.info(t("t2_none", lang))
    else:
        table = events.copy()
        table["start"] = table["start"].dt.strftime("%a %d.%m. %H:%M")
        table["end"] = table["end"].dt.strftime("%a %d.%m. %H:%M")
        table = table.rename(
            columns={
                "start": t("t2_col_start", lang),
                "end": t("t2_col_end", lang),
                "hours": t("t2_col_hours", lang),
                "weekend_hours": t("t2_col_weekend", lang),
                "wasted_mwh": t("t2_col_wasted", lang),
                "cost_eur": t("t2_col_cost", lang),
                "co2_t": t("t2_col_co2", lang),
            }
        )
        st.dataframe(
            table,
            hide_index=True,
            width="stretch",
            column_config={
                t("t2_col_wasted", lang): st.column_config.NumberColumn(format="%.1f"),
                t("t2_col_cost", lang): st.column_config.NumberColumn(format="%.0f"),
                t("t2_col_co2", lang): st.column_config.NumberColumn(format="%.1f"),
            },
        )
        st.caption("💡 " + t("t2_action", lang))

# ======================================================================================
# Tab 3 — Market & flexibility
# ======================================================================================
with tab3:
    pstats = an.price_statistics(df)
    p1, p2, p3, p4 = st.columns(4)
    p1.metric(t("t3_mean_price", lang), f"{fmt_num(pstats['mean'], 1, lang)} €/MWh")
    p2.metric(t("t3_weighted", lang), f"{fmt_num(pstats['load_weighted_price'], 1, lang)} €/MWh")
    p3.metric(t("t3_spread", lang), f"{fmt_num(pstats['spread_daily'], 1, lang)} €/MWh")
    p4.metric(t("t3_neg_hours", lang), f"{pstats['negative_hours']}")

    st.subheader(t("t3_market", lang))
    low_price_marker = float(np.percentile(df["price_eur_mwh"], 10))
    show_chart(ch.market_dual_axis(df, lang, max(low_price_marker, 0.0)))

    st.divider()
    st.subheader(f"🎛️ {t('t3_simulator', lang)}")
    s1, s2, s3, s4 = st.columns(4)
    flex_share = s1.slider(t("t3_flex_share", lang), 0, 30, 10, 1, help=t("t3_flex_help", lang))
    default_threshold = int(round(float(df["price_eur_mwh"].median()) / 5) * 5)
    price_threshold = s2.slider(
        t("t3_threshold", lang),
        int(np.floor(df["price_eur_mwh"].min() / 5) * 5),
        int(np.ceil(df["price_eur_mwh"].max() / 5) * 5),
        default_threshold,
        5,
    )
    window = s3.slider(t("t3_window", lang), 2, 24, 12, 1)
    efficiency = s4.slider(t("t3_eff", lang), 70, 100, 95, 1)

    result = cached_shift(df, flex_share / 100, float(price_threshold), int(window), efficiency / 100)
    r1, r2, r3, r4 = st.columns(4)
    r1.metric(t("t3_annual_saving", lang), fmt_eur(result.annual_cost_saving_eur, lang))
    r2.metric(t("t3_annual_co2", lang), f"{fmt_num(result.annual_co2_saving_t, 0, lang)} t")
    r3.metric(t("t3_shifted", lang), f"{fmt_num(result.shifted_mwh, 0, lang)} MWh")
    r4.metric(
        t("t3_peak", lang),
        f"{fmt_num(result.peak_after_mw, 1, lang)} MW",
        (
            f"{fmt_num(result.peak_after_mw - result.peak_before_mw, 1, lang)} MW"
            if abs(result.peak_after_mw - result.peak_before_mw) >= 0.05
            else None
        ),
        delta_color="inverse",
    )

    left, right = st.columns([3, 2])
    with left:
        st.markdown(f"**{t('t3_profile', lang)}**")
        show_chart(ch.shift_profile(result.profile, lang))
    with right:
        st.markdown(f"**{t('t3_ren', lang)} ↔ {t('t3_price', lang)}**")
        show_chart(ch.renewable_vs_price(df, lang))
    st.caption(t("t3_note", lang))

# ======================================================================================
# Tab 4 — Measurement & Verification
# ======================================================================================
with tab4:
    st.subheader(f"♻️ {t('t4_title', lang)}")
    st.markdown(f"<div class='insight'>{t('t4_intro', lang)}</div>", unsafe_allow_html=True)

    go_live_str = meta.get("events", {}).get("heat_recovery_go_live")
    if go_live_str:
        go_live = pd.Timestamp(go_live_str).tz_convert(an.TZ)
    else:  # dataset without metadata: infer from the flag column
        go_live = df_all.index[df_all["post_heat_recovery"]].min()

    try:
        mv = cached_mv(df, go_live, float(gas_price))
        if mv.reporting_days < 7:
            raise ValueError("reporting period too short")
    except ValueError:
        st.info(t("t4_need_baseline", lang))
        mv = None

    if mv is not None:
        v1, v2, v3, v4 = st.columns(4)
        v1.metric(t("t4_saving_mwh", lang), f"{fmt_num(mv.savings_mwh, 0, lang)} MWh", f"{mv.reporting_days} d", delta_color="off", delta_arrow="off")
        v2.metric(
            t("t4_saving_pct", lang),
            f"{fmt_num(mv.savings_pct, 1, lang)} %",
            f"± {fmt_num(abs(mv.uncertainty_pct) * mv.savings_pct / 100, 1, lang)} pp",
            delta_color="off", delta_arrow="off",
        )
        v3.metric(t("t4_saving_eur", lang), fmt_eur(mv.savings_eur, lang))
        v4.metric(t("t4_saving_co2", lang), f"{fmt_num(mv.savings_co2_t, 0, lang)} t CO₂")

        st.markdown(f"**{t('t4_baseline_vs_actual', lang)}**")
        show_chart(ch.mv_baseline_chart(mv.daily, mv.go_live, lang))

        left, right = st.columns(2)
        with left:
            st.markdown(f"**{t('t4_cusum', lang)}**")
            show_chart(ch.cusum_chart(mv.daily, mv.go_live, lang))
        with right:
            st.markdown(f"**{t('t4_scatter', lang)}**")
            show_chart(ch.mv_scatter(mv.daily, mv.coefficients, lang))

        st.markdown(f"**{t('t4_stats', lang)}**")
        c = mv.coefficients
        ok = lambda cond: f"✅ {t('t4_pass', lang)}" if cond else f"❌ {t('t4_fail', lang)}"  # noqa: E731
        quality = pd.DataFrame(
            [
                ["R²", f"{mv.r2:.3f}", "≥ 0.75", ok(mv.r2 >= 0.75)],
                ["CV(RMSE)", f"{mv.cv_rmse:.1f} %", "≤ 25 % (daily)", ok(mv.cv_rmse <= 25)],
                ["NMBE", f"{abs(mv.nmbe) if abs(mv.nmbe) < 0.005 else mv.nmbe:.2f} %", "± 10 % (daily)", ok(abs(mv.nmbe) <= 10)],
                [t("t4_uncertainty", lang), f"± {abs(mv.uncertainty_pct):.1f} % of savings", "< 50 %", ok(abs(mv.uncertainty_pct) < 50)],
                [t("t4_baseline_period", lang), f"{mv.baseline_days} d", "≥ 7 d", ok(mv.baseline_days >= 7)],
            ],
            columns=["Metric", "Value", "Criterion", "Status"],
        )
        q1, q2 = st.columns([3, 2])
        q1.dataframe(quality, hide_index=True, width="stretch")
        q2.markdown(
            f"**{t('t4_equation', lang)}**\n\n"
            f"`Gas = {c['intercept']:.1f} + {c['hdd']:.2f}·HDD + {c['units']:.3f}·Units`\n\n"
            f"{t('t4_go_live', lang)}: **{mv.go_live:%d.%m.%Y}**"
        )
        st.success(t("t4_iso", lang))

st.markdown(
    "<div class='source-note' style='margin-top:1.5rem'>Market data © Fraunhofer ISE Energy-Charts / "
    "Bundesnetzagentur SMARD.de (CC BY 4.0). Factory data is simulated for demonstration purposes.</div>",
    unsafe_allow_html=True,
)
