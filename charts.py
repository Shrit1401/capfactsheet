"""Altair charts shared by the tutor (inline visuals) and the 'How we built it' page."""

from __future__ import annotations

import altair as alt
import pandas as pd

import tutor_engine as te

FUND = "#f4655b"
BENCH = "#7c8db5"
SERIES = ["#f4655b", "#5b9cf4", "#a77cf4", "#3fbf8f", "#f4b65b"]


def _base(chart: alt.Chart) -> alt.Chart:
    return chart.configure_view(strokeWidth=0).configure_axis(grid=False, labelLimit=220)


def factsheet_chart(plan: te.LessonPlan, key: str) -> alt.Chart | None:
    c = plan.charts
    if key == "sector_allocation" and c.sector_allocation:
        df = pd.DataFrame([p.model_dump() for p in c.sector_allocation])
        ch = alt.Chart(df).mark_bar(cornerRadiusEnd=4, color=FUND).encode(
            x=alt.X("value:Q", title="% of fund"),
            y=alt.Y("label:N", sort="-x", title=None),
            tooltip=["label", alt.Tooltip("value:Q", format=".2f")],
        )
        text = ch.mark_text(align="left", dx=4).encode(text=alt.Text("value:Q", format=".1f"))
        return _base((ch + text).properties(height=max(160, 26 * len(df)), title="Where the money goes (sectors)"))
    if key == "market_cap_split" and c.market_cap_split:
        df = pd.DataFrame([p.model_dump() for p in c.market_cap_split])
        ch = alt.Chart(df).mark_arc(innerRadius=55).encode(
            theta="value:Q",
            color=alt.Color("label:N", scale=alt.Scale(range=SERIES), title=None),
            tooltip=["label", alt.Tooltip("value:Q", format=".2f")],
        )
        return _base(ch.properties(height=220, title="Company size mix"))
    if key == "returns_vs_benchmark" and c.returns:
        rows = []
        for r in c.returns:
            rows.append({"period": r.period, "series": "This fund", "value": r.fund})
            if r.benchmark is not None:
                rows.append({"period": r.period, "series": "Benchmark", "value": r.benchmark})
        df = pd.DataFrame(rows)
        order = [r.period for r in c.returns]
        ch = alt.Chart(df).mark_bar(cornerRadiusEnd=3).encode(
            x=alt.X("value:Q", title="Return (%)"),
            y=alt.Y("series:N", title=None, axis=None),
            row=alt.Row("period:N", sort=order, title=None, header=alt.Header(labelAngle=0, labelAlign="left")),
            color=alt.Color("series:N", scale=alt.Scale(domain=["This fund", "Benchmark"], range=[FUND, BENCH]),
                            title=None, legend=alt.Legend(orient="top")),
            tooltip=["period", "series", alt.Tooltip("value:Q", format=".2f")],
        ).properties(height=40, title=c.returns_note or "Returns vs benchmark")
        return ch.configure_view(strokeWidth=0).configure_axis(grid=False)
    return None


def rubric_comparison(grades: dict[str, dict[str, float | None]]) -> alt.Chart:
    rows = [{"model": m, "category": cat, "score": v}
            for m, cats in grades.items() for cat, v in cats.items() if v is not None]
    df = pd.DataFrame(rows)
    cats = list(te.RUBRIC)
    ch = alt.Chart(df).mark_bar(cornerRadiusEnd=3).encode(
        x=alt.X("score:Q", scale=alt.Scale(domain=[-3, 3]), title="Mean score (−3 … +3)"),
        y=alt.Y("model:N", title=None, axis=None),
        row=alt.Row("category:N", sort=cats, title=None, header=alt.Header(labelAngle=0, labelAlign="left")),
        color=alt.Color("model:N", scale=alt.Scale(range=SERIES), title=None, legend=alt.Legend(orient="top")),
        tooltip=["model", "category", alt.Tooltip("score:Q", format=".2f")],
    ).properties(height=22 * max(1, len(grades)))
    return ch.configure_view(strokeWidth=0).configure_axis(grid=False)
