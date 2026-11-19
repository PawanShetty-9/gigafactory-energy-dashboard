"""English / German UI strings. German uses the terms common in German energy management (EnMS)."""

from __future__ import annotations

TEXT: dict[str, dict[str, str]] = {
    # ---- general ---------------------------------------------------------------------------
    "title": {"en": "Gigafactory Energy & Flexibility Analytics", "de": "Gigafactory Energie- & Flexibilitätsanalyse"},
    "subtitle": {
        "en": "Multi-utility monitoring, leak detection, day-ahead flexibility and ISO 50001 M&V for a ~45 MW automotive & battery plant in Brandenburg",
        "de": "Multi-Utility-Monitoring, Leckageerkennung, Day-Ahead-Flexibilität und ISO-50001-M&V für ein ~45-MW-Automobil- & Batteriewerk in Brandenburg",
    },
    "language": {"en": "Language / Sprache", "de": "Sprache / Language"},
    "period": {"en": "Analysis period", "de": "Betrachtungszeitraum"},
    "settings": {"en": "Tariff assumptions", "de": "Tarifannahmen"},
    "grid_fees": {"en": "Grid fees, levies & taxes (€/MWh)", "de": "Netzentgelte, Umlagen & Steuern (€/MWh)"},
    "grid_fees_help": {
        "en": "Added on top of the hourly day-ahead price (spot pass-through contract).",
        "de": "Wird auf den stündlichen Day-Ahead-Preis aufgeschlagen (Spot-Durchreichungsvertrag).",
    },
    "gas_price": {"en": "Natural gas price incl. CO₂ (€/MWh)", "de": "Erdgaspreis inkl. CO₂ (€/MWh)"},
    "data_source": {"en": "Data sources", "de": "Datenquellen"},
    "price_source": {"en": "Day-ahead prices", "de": "Day-Ahead-Preise"},
    "ren_source": {"en": "Renewable share", "de": "EE-Anteil"},
    "factory_source": {"en": "Factory data", "de": "Werksdaten"},
    "factory_source_val": {"en": "Simulated Gigafactory (synthetic)", "de": "Simulierte Gigafactory (synthetisch)"},
    "refresh": {"en": "Fetch latest market data", "de": "Aktuelle Marktdaten laden"},
    "refresh_ok": {"en": "Dataset rebuilt.", "de": "Datensatz neu erstellt."},
    "refresh_fail": {"en": "Refresh failed", "de": "Aktualisierung fehlgeschlagen"},
    "generated": {"en": "Generated", "de": "Erstellt"},
    "no_data": {"en": "No data in the selected period.", "de": "Keine Daten im gewählten Zeitraum."},
    "missing_data": {
        "en": "Dataset not found. Generating it now (this takes a few seconds)…",
        "de": "Datensatz nicht gefunden. Er wird jetzt erstellt (dauert einige Sekunden)…",
    },
    "vs_prev": {"en": "vs. previous period", "de": "ggü. Vorperiode"},
    # ---- tabs ------------------------------------------------------------------------------
    "tab1": {"en": "📊 Executive Overview", "de": "📊 Gesamtübersicht"},
    "tab2": {"en": "🔍 Load Profile & Leaks", "de": "🔍 Lastganganalyse & Leckagen"},
    "tab3": {"en": "⚡ Power Market & Flexibility", "de": "⚡ Strommarkt & Flexibilität"},
    "tab4": {"en": "✅ Project M&V (ISO 50001)", "de": "✅ Projektvalidierung (ISO 50001)"},
    # ---- KPIs ------------------------------------------------------------------------------
    "kpi_energy": {"en": "Total energy", "de": "Gesamtenergie"},
    "kpi_cost": {"en": "Total energy cost", "de": "Energiekosten gesamt"},
    "kpi_co2": {"en": "CO₂ emissions", "de": "CO₂-Emissionen"},
    "kpi_intensity": {"en": "Energy intensity", "de": "Energieintensität"},
    "kpi_units": {"en": "Vehicles produced", "de": "Produzierte Fahrzeuge"},
    "kpi_avg_load": {"en": "Avg. electrical load", "de": "Ø elektrische Last"},
    "kpi_peak": {"en": "Peak load", "de": "Spitzenlast"},
    "kpi_price": {"en": "Load-weighted spot price", "de": "Lastgewichteter Spotpreis"},
    # ---- utilities ---------------------------------------------------------------------------
    "electricity": {"en": "Electricity", "de": "Strom"},
    "gas": {"en": "Natural gas", "de": "Erdgas"},
    "compressed_air": {"en": "Compressed air", "de": "Druckluft"},
    "cooling": {"en": "Cooling water", "de": "Kühlwasser"},
    "heating": {"en": "Heating water", "de": "Heizwasser"},
    "production_lines": {"en": "Production lines", "de": "Produktionslinien"},
    "chillers": {"en": "Chillers", "de": "Kältemaschinen"},
    "hvac_it": {"en": "HVAC, IT & lighting", "de": "RLT, IT & Beleuchtung"},
    "paint_shop": {"en": "Paint shop ovens", "de": "Lackiererei-Trockner"},
    "boilers": {"en": "Gas boilers", "de": "Gaskessel"},
    "losses": {"en": "Conversion losses", "de": "Umwandlungsverluste"},
    "pneumatics": {"en": "Pneumatic tools & robots", "de": "Pneumatik & Roboter"},
    "production_units": {"en": "Vehicles / h", "de": "Fahrzeuge / h"},
    # ---- tab 1 -------------------------------------------------------------------------------
    "t1_trend": {"en": "Multi-utility consumption", "de": "Multi-Utility-Verbrauch"},
    "t1_resolution": {"en": "Resolution", "de": "Auflösung"},
    "hourly": {"en": "Hourly", "de": "Stündlich"},
    "daily": {"en": "Daily", "de": "Täglich"},
    "t1_trend_note": {
        "en": "Compressed air and chiller electricity are sub-meters of electricity; cooling and heating water are thermal energy delivered (MWh_th).",
        "de": "Druckluft und Kältemaschinen sind Unterzähler des Stroms; Kühl- und Heizwasser sind gelieferte Wärme-/Kälteenergie (MWh_th).",
    },
    "t1_sankey": {"en": "Energy flow: carriers → utility systems → end use", "de": "Energieflussdiagramm: Energieträger → Versorgungssysteme → Nutzung"},
    "t1_mix": {"en": "Cost & CO₂ split", "de": "Kosten- & CO₂-Aufteilung"},
    "t1_intensity": {"en": "Daily energy intensity (kWh / vehicle)", "de": "Tägliche Energieintensität (kWh / Fahrzeug)"},
    # ---- tab 2 -------------------------------------------------------------------------------
    "t2_heatmap": {"en": "Load profile heatmap (mean MW by weekday and hour)", "de": "Lastgang-Heatmap (Ø MW nach Wochentag und Stunde)"},
    "t2_utility": {"en": "Utility", "de": "Medium"},
    "t2_baseload": {"en": "Baseload (P5)", "de": "Grundlast (P5)"},
    "t2_idle_ratio": {"en": "Idle / production load", "de": "Stillstand- / Produktionslast"},
    "t2_idle_share": {"en": "Energy used while not producing", "de": "Energie im Produktionsstillstand"},
    "t2_detection": {"en": "Automated anomaly detection: compressed air", "de": "Automatische Anomalieerkennung: Druckluft"},
    "t2_method": {"en": "Method", "de": "Methode"},
    "t2_zscore": {"en": "Robust Z-score on model residuals", "de": "Robuster Z-Score auf Modellresiduen"},
    "t2_iforest": {"en": "Isolation Forest", "de": "Isolation Forest"},
    "t2_threshold": {"en": "Z-score threshold", "de": "Z-Score-Schwelle"},
    "t2_contamination": {"en": "Expected anomaly share", "de": "Erwarteter Anomalieanteil"},
    "t2_explain": {
        "en": "Expected compressed-air power is modelled from production output (robust energy signature). Hours that run well above that expectation for at least 3 consecutive hours are flagged: a leak keeps blowing air when the lines stand still, so it shows up most clearly at weekends.",
        "de": "Der erwartete Druckluftbedarf wird aus der Produktionsmenge modelliert (robuste Energiesignatur). Stunden, die mindestens 3 Stunden in Folge deutlich darüber liegen, werden markiert: Eine Leckage bläst auch bei Stillstand weiter ab und fällt daher am Wochenende besonders auf.",
    },
    "t2_actual": {"en": "Actual", "de": "Ist"},
    "t2_expected": {"en": "Expected (model)", "de": "Erwartet (Modell)"},
    "t2_anomaly": {"en": "Anomaly", "de": "Anomalie"},
    "t2_events": {"en": "Detected events", "de": "Erkannte Ereignisse"},
    "t2_wasted": {"en": "Wasted energy", "de": "Verschwendete Energie"},
    "t2_wasted_cost": {"en": "Cost of waste", "de": "Kosten der Verschwendung"},
    "t2_annual": {"en": "If undetected for a year", "de": "Wenn ein Jahr unentdeckt"},
    "t2_none": {"en": "No anomalies detected in this period.", "de": "Keine Anomalien im gewählten Zeitraum."},
    "t2_col_start": {"en": "Start", "de": "Beginn"},
    "t2_col_end": {"en": "End", "de": "Ende"},
    "t2_col_hours": {"en": "Hours", "de": "Stunden"},
    "t2_col_weekend": {"en": "Weekend hours", "de": "Wochenendstunden"},
    "t2_col_wasted": {"en": "Wasted MWh", "de": "Verlust MWh"},
    "t2_col_cost": {"en": "Cost €", "de": "Kosten €"},
    "t2_col_co2": {"en": "CO₂ t", "de": "CO₂ t"},
    "t2_action": {
        "en": "Recommended action: ultrasonic leak survey of the compressed-air network, weekend shut-off valves per hall, and a pressure-decay test every Sunday.",
        "de": "Empfohlene Maßnahme: Ultraschall-Leckageortung im Druckluftnetz, Wochenend-Absperrventile je Halle und ein Druckabfalltest jeden Sonntag.",
    },
    # ---- tab 3 -------------------------------------------------------------------------------
    "t3_market": {"en": "Factory load vs. DE-LU day-ahead price (EPEX SPOT)", "de": "Werkslast vs. Day-Ahead-Preis DE-LU (EPEX SPOT)"},
    "t3_load": {"en": "Factory load (MW)", "de": "Werkslast (MW)"},
    "t3_price": {"en": "Day-ahead price (€/MWh)", "de": "Day-Ahead-Preis (€/MWh)"},
    "t3_ren": {"en": "Renewable share (%)", "de": "EE-Anteil (%)"},
    "t3_low_price": {"en": "Negative / low-price hours", "de": "Negative / günstige Stunden"},
    "t3_mean_price": {"en": "Mean spot price", "de": "Ø Spotpreis"},
    "t3_neg_hours": {"en": "Negative-price hours", "de": "Stunden mit negativem Preis"},
    "t3_spread": {"en": "Avg. daily spread", "de": "Ø Tages-Spread"},
    "t3_weighted": {"en": "Load-weighted price", "de": "Lastgewichteter Preis"},
    "t3_simulator": {"en": "Flexibility simulator (load shifting)", "de": "Flexibilitätssimulator (Lastverschiebung)"},
    "t3_flex_share": {"en": "Flexible load share (%)", "de": "Flexibler Lastanteil (%)"},
    "t3_flex_help": {
        "en": "Share of the electrical load that can be moved in time: thermal storage for cooling/heating water, compressed-air buffer tanks, EV fleet & AGV charging.",
        "de": "Anteil der elektrischen Last, der zeitlich verschoben werden kann: thermische Speicher für Kühl-/Heizwasser, Druckluftspeicher, Laden von E-Flotte & FTS.",
    },
    "t3_threshold": {"en": "Price threshold for shifting (€/MWh)", "de": "Preisschwelle für Verschiebung (€/MWh)"},
    "t3_window": {"en": "Max. shift window (± hours)", "de": "Max. Verschiebefenster (± Stunden)"},
    "t3_eff": {"en": "Storage round-trip efficiency (%)", "de": "Speicher-Wirkungsgrad (%)"},
    "t3_annual_saving": {"en": "Annualised cost savings", "de": "Hochgerechnete Kosteneinsparung p.a."},
    "t3_annual_co2": {"en": "Annualised CO₂ reduction", "de": "Hochgerechnete CO₂-Minderung p.a."},
    "t3_shifted": {"en": "Energy shifted (period)", "de": "Verschobene Energie (Zeitraum)"},
    "t3_peak": {"en": "Peak load after shifting", "de": "Spitzenlast nach Verschiebung"},
    "t3_profile": {"en": "Average daily profile: original vs. optimised", "de": "Mittleres Tagesprofil: Original vs. optimiert"},
    "t3_original": {"en": "Original load", "de": "Ursprüngliche Last"},
    "t3_optimised": {"en": "Optimised load", "de": "Optimierte Last"},
    "t3_hour": {"en": "Hour of day", "de": "Stunde"},
    "t3_note": {
        "en": "Annualised by scaling the selected period to 365 days. Savings count the wholesale component; extra MWh from storage losses pay grid fees. The original peak load is never exceeded, so the capacity charge (Leistungspreis) does not rise.",
        "de": "Hochrechnung des gewählten Zeitraums auf 365 Tage. Einsparungen beziehen sich auf den Großhandelsanteil; zusätzliche MWh aus Speicherverlusten tragen Netzentgelte. Die ursprüngliche Spitzenlast wird nie überschritten, der Leistungspreis steigt also nicht.",
    },
    # ---- tab 4 -------------------------------------------------------------------------------
    "t4_title": {"en": "Compressor Waste Heat Recovery: verified savings", "de": "Abwärmenutzung der Druckluftkompressoren: verifizierte Einsparung"},
    "t4_intro": {
        "en": "Waste heat from the compressor station pre-heats the heating water loop. Savings are verified with a regression baseline (IPMVP Option C): daily gas = b₀ + b₁·HDD + b₂·vehicles, fitted on the pre-project period and projected into the reporting period.",
        "de": "Abwärme der Kompressorstation wärmt den Heizwasserkreis vor. Die Einsparung wird mit einer Regressions-Baseline verifiziert (IPMVP Option C): Erdgas pro Tag = b₀ + b₁·Heizgradtage + b₂·Fahrzeuge, kalibriert auf den Zeitraum vor Projektstart und auf den Berichtszeitraum projiziert.",
    },
    "t4_go_live": {"en": "Go-live", "de": "Inbetriebnahme"},
    "t4_saving_mwh": {"en": "Verified gas savings", "de": "Verifizierte Gaseinsparung"},
    "t4_saving_pct": {"en": "Savings vs. adjusted baseline", "de": "Einsparung ggü. bereinigter Baseline"},
    "t4_saving_eur": {"en": "Cost savings", "de": "Kosteneinsparung"},
    "t4_saving_co2": {"en": "Avoided CO₂", "de": "Vermiedenes CO₂"},
    "t4_baseline_vs_actual": {"en": "Adjusted baseline vs. actual gas consumption (daily)", "de": "Bereinigte Baseline vs. tatsächlicher Gasverbrauch (täglich)"},
    "t4_predicted": {"en": "Adjusted baseline (model)", "de": "Bereinigte Baseline (Modell)"},
    "t4_actual": {"en": "Actual", "de": "Ist"},
    "t4_cusum": {"en": "CUSUM: cumulative sum of differences (actual − baseline)", "de": "CUSUM: kumulierte Abweichung (Ist − Baseline)"},
    "t4_scatter": {"en": "Energy signature: gas vs. heating degree days", "de": "Energiesignatur: Erdgas vs. Heizgradtage"},
    "t4_baseline_period": {"en": "Baseline period", "de": "Basiszeitraum"},
    "t4_reporting_period": {"en": "Reporting period", "de": "Berichtszeitraum"},
    "t4_stats": {"en": "Model quality (ASHRAE Guideline 14)", "de": "Modellgüte (ASHRAE Guideline 14)"},
    "t4_pass": {"en": "pass", "de": "erfüllt"},
    "t4_fail": {"en": "fail", "de": "nicht erfüllt"},
    "t4_uncertainty": {"en": "Savings uncertainty (68 %)", "de": "Unsicherheit der Einsparung (68 %)"},
    "t4_iso": {
        "en": "ISO 50001 / EMAS evidence: the baseline (EnB) is normalised for weather and production (relevant variables, ISO 50006), the model meets ASHRAE 14 accuracy criteria, and the CUSUM slope changes sharply at go-live, showing a persistent, statistically verified improvement of energy performance (EnPI).",
        "de": "Nachweis für ISO 50001 / EMAS: Die energetische Ausgangsbasis (EnB) ist um Witterung und Produktion bereinigt (relevante Variablen nach ISO 50006), das Modell erfüllt die Genauigkeitskriterien nach ASHRAE 14, und die CUSUM-Kurve knickt bei Inbetriebnahme deutlich ab: eine dauerhafte, statistisch belegte Verbesserung der energiebezogenen Leistung (EnPI).",
    },
    "t4_need_baseline": {
        "en": "Select a period that includes at least 7 days before and after go-live to run the M&V analysis.",
        "de": "Wählen Sie einen Zeitraum mit mindestens 7 Tagen vor und nach der Inbetriebnahme für die M&V-Analyse.",
    },
    "t4_hdd": {"en": "Heating degree days (base 16 °C)", "de": "Heizgradtage (Basis 16 °C)"},
    "t4_gas_day": {"en": "Gas (MWh/day)", "de": "Erdgas (MWh/Tag)"},
    "t4_equation": {"en": "Baseline equation", "de": "Baseline-Gleichung"},
    # ---- weekdays ------------------------------------------------------------------------------
    "weekdays": {"en": "Mon,Tue,Wed,Thu,Fri,Sat,Sun", "de": "Mo,Di,Mi,Do,Fr,Sa,So"},
}


def t(key: str, lang: str = "en") -> str:
    """Translate a UI key; falls back to English, then to the key itself."""
    entry = TEXT.get(key)
    if entry is None:
        return key
    return entry.get(lang) or entry.get("en") or key


def weekdays(lang: str = "en") -> list[str]:
    return t("weekdays", lang).split(",")
