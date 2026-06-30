"""
Run locally:
    pip install -r requirements.txt
    streamlit run app.py
"""

from datetime import date, datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components

from analytics import hours_by_category
from database import (
    get_blocks_for_dates,
    get_categories,
    get_category_colors,
    get_day_blocks,
    get_month_activity,
    initialize_database,
    update_day_blocks,
)
from utils import week_dates


st.set_page_config(page_title="Time Ledger", layout="wide")

initialize_database()

BASE_DIR = Path(__file__).resolve().parent
calendar_component = components.declare_component(
    "ledger_calendar",
    path=str(BASE_DIR / "calendar_component"),
)


def query_param_date() -> date:
    raw_value = st.query_params.get("date")

    if isinstance(raw_value, list):
        raw_value = raw_value[0] if raw_value else None

    if raw_value:
        try:
            return datetime.strptime(raw_value, "%Y-%m-%d").date()
        except ValueError:
            pass

    return date.today()


def set_selected_day(value: date) -> None:
    st.session_state["selected_day"] = value
    st.session_state["calendar_month"] = value.replace(day=1)


def set_calendar_month(value: date) -> None:
    st.session_state["calendar_month"] = value


def render_category_legend(category_colors: dict[str, str]) -> None:
    if not category_colors:
        return

    items = "".join(
        f"""
        <div class="category-legend-item">
            <span class="category-swatch" style="background: {color};"></span>
            <span>{category}</span>
        </div>
        """
        for category, color in category_colors.items()
    )

    st.markdown(
        f"""
        <style>
            .category-legend {{
                display: grid;
                gap: 0.35rem;
                margin-top: 0.75rem;
            }}
            .category-legend-item {{
                align-items: center;
                display: flex;
                gap: 0.45rem;
                font-size: 0.85rem;
            }}
            .category-swatch {{
                border: 1px solid #000000;
                border-radius: 999px;
                display: inline-block;
                height: 0.7rem;
                width: 0.7rem;
            }}
        </style>
        <div class="category-legend">{items}</div>
        """,
        unsafe_allow_html=True,
    )


def render_calendar(selected_day: date) -> None:
    if "calendar_month" not in st.session_state:
        st.session_state["calendar_month"] = selected_day.replace(day=1)

    visible_month = st.session_state["calendar_month"]
    activity = get_month_activity(visible_month.year, visible_month.month)

    event = calendar_component(
        selected_date=selected_day.isoformat(),
        year=visible_month.year,
        month=visible_month.month,
        activity_dates=list(activity.keys()),
        key="ledger_calendar_component",
        default=None,
    )

    if not event:
        return

    event_id = event.get("event_id")
    if event_id == st.session_state.get("last_calendar_event_id"):
        return

    st.session_state["last_calendar_event_id"] = event_id

    if event.get("action") == "select_day":
        selected = datetime.strptime(event["date"], "%Y-%m-%d").date()
        set_selected_day(selected)
        st.rerun()

    if event.get("action") == "month":
        set_calendar_month(date(int(event["year"]), int(event["month"]), 1))
        st.rerun()


def render_analytics(
    title: str,
    blocks: pd.DataFrame,
    chart_key: str,
    category_colors: dict[str, str],
) -> None:
    st.subheader(title)
    totals = hours_by_category(blocks)

    if totals.empty:
        st.info("No categorized time blocks yet.")
        return

    st.dataframe(totals, hide_index=True, use_container_width=True)
    fig = px.pie(
        totals,
        names="category",
        values="hours",
        color="category",
        color_discrete_map=category_colors,
        category_orders={"category": totals["category"].tolist()},
        labels={"category": "Category", "hours": "Hours"},
        hole=0.35,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(showlegend=False, margin=dict(t=20, b=20, l=20, r=20))
    st.plotly_chart(fig, use_container_width=True, key=chart_key)


def text_color_for_background(hex_color: str) -> str:
    value = hex_color.lstrip("#")
    if len(value) != 6:
        return "#ffffff"

    red = int(value[0:2], 16)
    green = int(value[2:4], 16)
    blue = int(value[4:6], 16)
    brightness = (red * 299 + green * 587 + blue * 114) / 1000
    return "#000000" if brightness > 150 else "#ffffff"


def color_category_cell(value, category_colors: dict[str, str]) -> str:
    color = category_colors.get(value)
    if not color:
        return ""

    text_color = text_color_for_background(color)
    return f"background-color: {color}; color: {text_color}; font-weight: 700;"


def render_daily_tab(
    selected_day: date,
    categories: list[str],
    category_colors: dict[str, str],
) -> None:
    st.header("Daily Grid")
    st.caption(f"Selected day: {selected_day:%A, %B %d, %Y}")

    day_blocks = get_day_blocks(selected_day)
    editable = day_blocks[["slot_index", "Time", "Category", "Note"]].copy()
    editable[" "] = ""

    edited = st.data_editor(
        editable,
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        disabled=["slot_index", "Time", " "],
        column_config={
            "slot_index": None,
            "Time": st.column_config.TextColumn("Time", disabled=True),
            "Category": st.column_config.SelectboxColumn(
                "Category",
                options=[""] + categories,
                required=False,
                width="medium",
            ),
            "Note": st.column_config.TextColumn("Note", width="large"),
            " ": st.column_config.TextColumn(" ", width="small", disabled=True),
        },
        key=f"daily_grid_{selected_day.isoformat()}",
    )

    if st.button("Save daily changes", type="primary"):
        update_day_blocks(selected_day, edited.drop(columns=[" "]))
        st.success("Daily grid saved.")
        st.rerun()


def render_week_tab(selected_day: date, category_colors: dict[str, str]) -> None:
    st.header("Week View")
    days = week_dates(selected_day)
    blocks = get_blocks_for_dates(days)

    blocks["Time"] = blocks["start_time"] + " - " + blocks["end_time"]
    blocks["Day"] = pd.to_datetime(blocks["date"]).dt.strftime("%a %m/%d")

    week_grid = blocks.pivot(index="Time", columns="Day", values="category").reset_index()
    ordered_columns = ["Time"] + [day.strftime("%a %m/%d") for day in days]
    week_grid = week_grid.reindex(columns=ordered_columns)

    styled_grid = week_grid.style.map(
        lambda value: color_category_cell(value, category_colors),
        subset=ordered_columns[1:],
    )
    st.dataframe(styled_grid, hide_index=True, use_container_width=True, height=720)


def render_analytics_tab(selected_day: date, category_colors: dict[str, str]) -> None:
    st.header("Analytics")
    day_blocks = get_day_blocks(selected_day)
    days = week_dates(selected_day)
    week_blocks = get_blocks_for_dates(days)
    day_title = selected_day.strftime("%A, %B %d, %Y")
    week_title = f"{days[0]:%b %d, %Y} - {days[-1]:%b %d, %Y}"

    day_col, week_col = st.columns(2)
    with day_col:
        render_analytics(day_title, day_blocks, "selected_day_hours_chart", category_colors)
    with week_col:
        render_analytics(week_title, week_blocks, "selected_week_hours_chart", category_colors)


def main() -> None:
    st.markdown(
        """
        <style>
            section[data-testid="stSidebar"] {
                background: #ffffff;
            }
            section[data-testid="stSidebar"] * {
                color: #000000;
            }
            section[data-testid="stSidebar"] button {
                color: inherit;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title("Time Ledger")
    st.caption("Log your day in 15-minute blocks.")

    categories = get_categories()
    category_colors = get_category_colors()
    if "selected_day" not in st.session_state:
        st.session_state["selected_day"] = query_param_date()

    selected_day = st.session_state["selected_day"]
    if "calendar_month" not in st.session_state:
        st.session_state["calendar_month"] = selected_day.replace(day=1)

    with st.sidebar:
        st.header("Calendar")
        render_calendar(selected_day)
        st.caption(f"Selected: {selected_day:%b %d, %Y}")
        st.subheader("Categories")
        render_category_legend(category_colors)

    daily_tab, week_tab, analytics_tab = st.tabs(["Daily", "Week", "Analytics"])

    with daily_tab:
        render_daily_tab(selected_day, categories, category_colors)
    with week_tab:
        render_week_tab(selected_day, category_colors)
    with analytics_tab:
        render_analytics_tab(selected_day, category_colors)


if __name__ == "__main__":
    main()
