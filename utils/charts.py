"""
Plotly figures for the dashboard.

Every figure uses transparent backgrounds and Streamlit's theme, so it renders correctly
in both light and dark mode. Colours are fixed per energy carrier across all charts.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from utils.i18n import t, weekdays

COLORS = {
    "electricity": "#3B82F6",
    "gas": "#F59E0B",
    "compressed_air": "#8B5CF6",
    "cooling": "#06B6D4",
    "heating": "#EF4444",
    "price": "#E11D48",
    "renewable": "#22C55E",
    "anomaly": "#DC2626",
    "neutral": "#94A3B8",
    "optimised": "#10B981",
}

# Sankey node colours (by i18n key)
NODE_COLORS = {
    "electricity": COLORS["electricity"],
    "gas": COLORS["gas"],
    "production_lines": "#60A5FA",
    "compressed_air": COLORS["compressed_air"],
    "chillers": "#22D3EE",
    "hvac_it": "#93C5FD",
    "paint_shop": "#FBBF24",
    "boilers": "#FB923C",
    "heating": COLORS["heating"],
    "cooling": COLORS["cooling"],
    "losses": COLORS["neutral"],
    "pneumatics": "#A78BFA",
}


def _layout(fig: go.Figure, height: int = 420, **kwargs) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=40, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        hovermode="x unified",
        **kwargs,
    )
    return fig


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


# ======================================================================================
# Tab 1 — Executive overview
# ======================================================================================
def utility_trend(df: pd.DataFrame, lang: str, resolution: str = "daily") -> go.Figure:
    """Line chart of all five utilities, hourly (MW) or daily (MWh)."""
    cols = {
        "electricity": "electricity_mwh",
        "gas": "gas_mwh",
        "compressed_air": "compressed_air_mwh",
        "cooling": "cooling_water_mwh_th",
        "heating": "heating_water_mwh_th",
    }
    data = df[list(cols.values())]
    if resolution == "daily":
        data = data.resample("D").sum()
        y_title = "MWh / " + ("day" if lang == "en" else "Tag")
    else:
        y_title = "MW"
    fig = go.Figure()
    for key, col in cols.items():
        fig.add_trace(
            go.Scatter(
                x=data.index,
                y=data[col],
                name=t(key, lang),
                mode="lines",
                line=dict(color=COLORS[key], width=2 if key in ("electricity", "gas") else 1.6),
                fill="tozeroy" if key == "electricity" else None,
                fillcolor=_hex_to_rgba(COLORS[key], 0.08),
                hovertemplate="%{y:,.1f}",
            )
        )
    fig.update_yaxes(title=y_title, rangemode="tozero")
    return _layout(fig, 420)


def energy_sankey(flows: list[tuple[str, str, float]], lang: str) -> go.Figure:
    nodes = []
    for a, b, _ in flows:
        for n in (a, b):
            if n not in nodes:
                nodes.append(n)
    index = {n: i for i, n in enumerate(nodes)}
    totals = {n: 0.0 for n in nodes}
    for a, b, v in flows:
        totals[b] += v
    for a, _, v in flows:
        if a in ("electricity", "gas"):
            totals[a] += v
    fig = go.Figure(
        go.Sankey(
            arrangement="snap",
            valueformat=",.0f",
            valuesuffix=" MWh",
            node=dict(
                pad=18,
                thickness=16,
                line=dict(width=0),
                label=[f"{t(n, lang)}" for n in nodes],
                color=[NODE_COLORS.get(n, COLORS["neutral"]) for n in nodes],
                hovertemplate="%{label}: %{value:,.0f} MWh<extra></extra>",
            ),
            link=dict(
                source=[index[a] for a, _, _ in flows],
                target=[index[b] for _, b, _ in flows],
                value=[v for _, _, v in flows],
                color=[_hex_to_rgba(NODE_COLORS.get(a, COLORS["neutral"]), 0.35) for a, _, _ in flows],
            ),
        )
    )
    fig.update_layout(hovermode=False)
    return _layout(fig, 440, font=dict(size=13))


def cost_co2_split(df: pd.DataFrame, lang: str) -> go.Figure:
    """Two donuts: energy cost and CO2 by carrier."""
    fig = make_subplots(
        rows=1,
        cols=2,
        specs=[[{"type": "domain"}, {"type": "domain"}]],
    )
    labels = [t("electricity", lang), t("gas", lang)]
    colors = [COLORS["electricity"], COLORS["gas"]]
    fig.add_trace(
        go.Pie(
            labels=labels,
            values=[df["electricity_cost_eur"].sum(), df["gas_cost_eur"].sum()],
            hole=0.6,
            marker=dict(colors=colors),
            textinfo="percent",
            hovertemplate="%{label}: €%{value:,.0f}<extra></extra>",
            sort=False,
        ),
        1,
        1,
    )
    fig.add_trace(
        go.Pie(
            labels=labels,
            values=[df["co2_electricity_t"].sum(), df["co2_gas_t"].sum()],
            hole=0.6,
            marker=dict(colors=colors),
            textinfo="percent",
            hovertemplate="%{label}: %{value:,.0f} t<extra></extra>",
            sort=False,
        ),
        1,
        2,
    )
    fig.update_layout(
        hovermode=False,
        annotations=[
            dict(text="<b>€</b>", x=0.225, y=0.5, showarrow=False, font=dict(size=18)),
            dict(text="<b>CO₂</b>", x=0.775, y=0.5, showarrow=False, font=dict(size=16)),
        ],
    )
    fig = _layout(fig, 300)
    fig.update_layout(legend=dict(orientation="h", yanchor="top", y=-0.02, xanchor="center", x=0.5))
    return fig


def intensity_chart(df: pd.DataFrame, lang: str) -> go.Figure:
    """Daily kWh per vehicle (bars) — days without production are omitted."""
    daily = df[["total_energy_mwh", "production_units"]].resample("D").sum()
    daily = daily[daily["production_units"] > 50]
    intensity = daily["total_energy_mwh"] * 1000 / daily["production_units"]
    fig = go.Figure(
        go.Bar(
            x=intensity.index,
            y=intensity,
            marker_color=COLORS["electricity"],
            hovertemplate="%{x|%a %d %b}: %{y:,.0f} kWh<extra></extra>",
        )
    )
    if len(intensity):
        fig.add_hline(y=intensity.median(), line_dash="dot", line_color=COLORS["neutral"])
    fig.update_yaxes(title="kWh / " + ("vehicle" if lang == "en" else "Fzg."))
    fig.update_layout(hovermode="closest")
    return _layout(fig, 300)


# ======================================================================================
# Tab 2 — Load profile & anomalies
# ======================================================================================
def load_heatmap(matrix: pd.DataFrame, lang: str, unit: str = "MW") -> go.Figure:
    fig = go.Figure(
        go.Heatmap(
            z=matrix.values,
            x=[f"{h:02d}" for h in matrix.columns],
            y=weekdays(lang),
            colorscale="Turbo",
            colorbar=dict(title=unit, thickness=12),
            hovertemplate="%{y} %{x}:00 → %{z:.2f} " + unit + "<extra></extra>",
        )
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(title=t("t3_hour", lang))
    fig.update_layout(hovermode="closest")
    return _layout(fig, 360)


def anomaly_chart(anomalies: pd.DataFrame, lang: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=anomalies.index,
            y=anomalies["expected"],
            name=t("t2_expected", lang),
            mode="lines",
            line=dict(color=COLORS["neutral"], width=1.5, dash="dot"),
            hovertemplate="%{y:.2f} MW",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=anomalies.index,
            y=anomalies["actual"],
            name=t("t2_actual", lang),
            mode="lines",
            line=dict(color=COLORS["compressed_air"], width=1.6),
            hovertemplate="%{y:.2f} MW",
        )
    )
    flagged = anomalies[anomalies["is_anomaly"]]
    fig.add_trace(
        go.Scatter(
            x=flagged.index,
            y=flagged["actual"],
            name=t("t2_anomaly", lang),
            mode="markers",
            marker=dict(color=COLORS["anomaly"], size=7, symbol="x"),
            hovertemplate="%{y:.2f} MW",
        )
    )
    # Shade weekends to make the "leak blows at standstill" story obvious
    days = pd.date_range(anomalies.index.min().normalize(), anomalies.index.max(), freq="D")
    for d in days[days.dayofweek == 5]:
        fig.add_vrect(x0=d, x1=d + pd.Timedelta(days=2), fillcolor=COLORS["neutral"], opacity=0.08, line_width=0)
    fig.update_yaxes(title="MW (el.)", rangemode="tozero")
    return _layout(fig, 400)


# ======================================================================================
# Tab 3 — Market & flexibility
# ======================================================================================
def market_dual_axis(df: pd.DataFrame, lang: str, low_price: float) -> go.Figure:
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["electricity_mwh"],
            name=t("t3_load", lang),
            mode="lines",
            line=dict(color=COLORS["electricity"], width=1.4),
            fill="tozeroy",
            fillcolor=_hex_to_rgba(COLORS["electricity"], 0.12),
            hovertemplate="%{y:.1f} MW",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["price_eur_mwh"],
            name=t("t3_price", lang),
            mode="lines",
            line=dict(color=COLORS["price"], width=1.4),
            hovertemplate="%{y:.1f} €/MWh",
        ),
        secondary_y=True,
    )
    cheap = df[df["price_eur_mwh"] <= low_price]
    fig.add_trace(
        go.Scatter(
            x=cheap.index,
            y=cheap["price_eur_mwh"],
            name=t("t3_low_price", lang) + f" (≤ {low_price:.0f} €)",
            mode="markers",
            marker=dict(color=COLORS["renewable"], size=6),
            hovertemplate="%{y:.1f} €/MWh",
        ),
        secondary_y=True,
    )
    if (df["price_eur_mwh"] < 0).any():
        fig.add_hline(y=0, line_color=COLORS["neutral"], line_width=1, secondary_y=True)
    fig.update_yaxes(title_text=t("t3_load", lang), secondary_y=False, rangemode="tozero")
    fig.update_yaxes(title_text=t("t3_price", lang), secondary_y=True, showgrid=False)
    return _layout(fig, 430)


def renewable_vs_price(df: pd.DataFrame, lang: str) -> go.Figure:
    """Merit-order effect: price falls as the renewable share rises."""
    fig = go.Figure(
        go.Scattergl(
            x=df["renewable_share_pct"],
            y=df["price_eur_mwh"],
            mode="markers",
            marker=dict(
                size=5,
                color=df.index.hour,
                colorscale="Viridis",
                colorbar=dict(title="h", thickness=10),
                opacity=0.7,
            ),
            hovertemplate="%{x:.0f} % → %{y:.0f} €/MWh<extra></extra>",
        )
    )
    fig.update_xaxes(title=t("t3_ren", lang))
    fig.update_yaxes(title=t("t3_price", lang))
    fig.update_layout(hovermode="closest")
    return _layout(fig, 360)


def shift_profile(profile: pd.DataFrame, lang: str) -> go.Figure:
    """Average 24 h profile before/after optimisation, with the average price."""
    hourly = profile.groupby(profile.index.hour).mean()
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Scatter(
            x=hourly.index,
            y=hourly["original_mw"],
            name=t("t3_original", lang),
            line=dict(color=COLORS["neutral"], width=2, dash="dot"),
            hovertemplate="%{y:.2f} MW",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=hourly.index,
            y=hourly["shifted_mw"],
            name=t("t3_optimised", lang),
            line=dict(color=COLORS["optimised"], width=2.5),
            fill="tonexty",
            fillcolor=_hex_to_rgba(COLORS["optimised"], 0.15),
            hovertemplate="%{y:.2f} MW",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=hourly.index,
            y=hourly["price"],
            name=t("t3_price", lang),
            mode="lines",
            line=dict(color=COLORS["price"], width=1.5, dash="dash", shape="spline"),
            hovertemplate="%{y:.0f} €/MWh",
        ),
        secondary_y=True,
    )
    fig.update_xaxes(title=t("t3_hour", lang), dtick=2)
    fig.update_yaxes(title_text="MW", secondary_y=False)
    fig.update_yaxes(title_text="€/MWh", secondary_y=True, showgrid=False)
    return _layout(fig, 380)


# ======================================================================================
# Tab 4 — M&V
# ======================================================================================
def mv_baseline_chart(daily: pd.DataFrame, go_live: pd.Timestamp, lang: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=daily.index,
            y=daily["predicted"],
            name=t("t4_predicted", lang),
            line=dict(color=COLORS["neutral"], width=2, dash="dash"),
            hovertemplate="%{y:,.0f} MWh",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=daily.index,
            y=daily["actual"],
            name=t("t4_actual", lang),
            line=dict(color=COLORS["gas"], width=2.5),
            fill="tonexty",
            fillcolor=_hex_to_rgba(COLORS["optimised"], 0.18),
            hovertemplate="%{y:,.0f} MWh",
        )
    )
    _go_live_marker(fig, go_live, lang)
    fig.update_yaxes(title=t("t4_gas_day", lang), rangemode="tozero")
    return _layout(fig, 380)


def cusum_chart(daily: pd.DataFrame, go_live: pd.Timestamp, lang: str) -> go.Figure:
    colors = np.where(daily["period"] == "reporting", COLORS["optimised"], COLORS["neutral"])
    fig = go.Figure(
        go.Scatter(
            x=daily.index,
            y=daily["cusum"],
            mode="lines+markers",
            line=dict(color=COLORS["optimised"], width=2),
            marker=dict(color=colors, size=6),
            name="CUSUM",
            hovertemplate="%{y:,.0f} MWh",
        )
    )
    fig.add_hline(y=0, line_color=COLORS["neutral"], line_width=1)
    _go_live_marker(fig, go_live, lang)
    fig.update_yaxes(title="Σ (Ist − Baseline) MWh" if lang == "de" else "Σ (actual − baseline) MWh")
    return _layout(fig, 340)


def mv_scatter(daily: pd.DataFrame, coefficients: dict, lang: str) -> go.Figure:
    fig = go.Figure()
    for period, color, label in (
        ("baseline", COLORS["neutral"], t("t4_baseline_period", lang)),
        ("reporting", COLORS["gas"], t("t4_reporting_period", lang)),
    ):
        part = daily[daily["period"] == period]
        fig.add_trace(
            go.Scatter(
                x=part["hdd"],
                y=part["actual"],
                mode="markers",
                name=label,
                marker=dict(color=color, size=8, opacity=0.85),
                customdata=part["units"],
                hovertemplate="HDD %{x:.1f} · %{customdata:,.0f} Fzg. → %{y:,.0f} MWh<extra></extra>",
            )
        )
    # Baseline line at the median production level of the dataset
    if len(daily):
        x = np.linspace(0, max(daily["hdd"].max(), 1), 50)
        median_units = daily["units"].median()
        y = coefficients["intercept"] + coefficients["hdd"] * x + coefficients["units"] * median_units
        fig.add_trace(
            go.Scatter(
                x=x,
                y=y,
                mode="lines",
                name=t("t4_predicted", lang),
                line=dict(color=COLORS["neutral"], dash="dash"),
                hoverinfo="skip",
            )
        )
    fig.update_xaxes(title=t("t4_hdd", lang))
    fig.update_yaxes(title=t("t4_gas_day", lang))
    fig.update_layout(hovermode="closest")
    return _layout(fig, 340)


def _go_live_marker(fig: go.Figure, go_live: pd.Timestamp, lang: str) -> None:
    x = pd.Timestamp(go_live)
    fig.add_shape(type="line", x0=x, x1=x, y0=0, y1=1, yref="paper", line=dict(color=COLORS["optimised"], dash="dot"))
    fig.add_annotation(
        x=x, y=1, yref="paper", text=t("t4_go_live", lang), showarrow=False, xanchor="left", yanchor="top",
        font=dict(color=COLORS["optimised"]),
    )
