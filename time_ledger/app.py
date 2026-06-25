"""
Run locally:
    pip install -r requirements.txt
    streamlit run app.py
"""

import calendar
from datetime import date, datetime
from html import escape

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics import hours_by_category
from database import (
    get_blocks_for_dates,
    get_categories,
    get_day_blocks,
    get_month_activity,
    initialize_database,
    update_day_blocks,
)
from utils import week_dates


st.set_page_config(page_title="Time Ledger", layout="wide")

initialize_database()


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


def shift_month(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def set_selected_day(value: date) -> None:
    st.query_params["date"] = value.isoformat()
    st.session_state["selected_day"] = value
    st.session_state["calendar_month"] = value.replace(day=1)


def render_calendar(selected_day: date) -> None:
    if "calendar_month" not in st.session_state:
        st.session_state["calendar_month"] = selected_day.replace(day=1)

    visible_month = st.session_state["calendar_month"]

    left_col, title_col, right_col = st.columns([1, 4, 1])
    with left_col:
        if st.button("‹", key="previous_month", help="Previous month"):
            st.session_state["calendar_month"] = shift_month(visible_month, -1)
            st.rerun()
    with title_col:
        st.subheader(f"{calendar.month_name[visible_month.month]} {visible_month.year}")
    with right_col:
        if st.button("›", key="next_month", help="Next month"):
            st.session_state["calendar_month"] = shift_month(visible_month, 1)
            st.rerun()

    activity = get_month_activity(visible_month.year, visible_month.month)
    month_rows = calendar.Calendar(firstweekday=0).monthdatescalendar(
        visible_month.year,
        visible_month.month,
    )

    html_rows = []
    for week in month_rows:
        day_cells = []
        for day_value in week:
            if day_value.month != visible_month.month:
                day_cells.append('<td class="muted"></td>')
                continue

            day_text = day_value.isoformat()
            classes = ["day-cell"]
            classes.append("has-data" if activity.get(day_text) else "empty")
            if day_value == selected_day:
                classes.append("selected")

            day_cells.append(
                "<td>"
                f'<a class="{" ".join(classes)}" href="?date={day_text}">'
                f'<span class="day-number">{day_value.day}</span>'
                "</a>"
                "</td>"
            )
        html_rows.append(f"<tr>{''.join(day_cells)}</tr>")

    weekday_headers = "".join(f"<th>{escape(name)}</th>" for name in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
    st.markdown(
        f"""
        <style>
            .ledger-calendar {{
                width: 100%;
                border-collapse: separate;
                border-spacing: 8px;
                table-layout: fixed;
                margin-bottom: 1rem;
            }}
            .ledger-calendar th {{
                color: #9ca3af;
                font-size: 0.85rem;
                font-weight: 600;
                text-align: center;
            }}
            .ledger-calendar td {{
                height: 58px;
                padding: 0;
            }}
            .ledger-calendar .day-cell {{
                align-items: flex-start;
                border-radius: 8px;
                box-sizing: border-box;
                color: #e5e7eb;
                display: flex;
                height: 58px;
                justify-content: flex-end;
                padding: 8px;
                text-decoration: none;
                width: 100%;
            }}
            .ledger-calendar .empty {{
                background: #374151;
                border: 1px solid #4b5563;
            }}
            .ledger-calendar .has-data {{
                background: #14532d;
                border: 1px solid #22c55e;
            }}
            .ledger-calendar .selected {{
                box-shadow: 0 0 0 2px #f8fafc inset;
            }}
            .ledger-calendar .muted {{
                background: transparent;
            }}
            .ledger-calendar .day-number {{
                font-weight: 700;
            }}
            .calendar-legend {{
                color: #9ca3af;
                font-size: 0.9rem;
                margin-bottom: 1rem;
            }}
            .calendar-dot {{
                border-radius: 999px;
                display: inline-block;
                height: 0.7rem;
                margin: 0 0.25rem 0 0.75rem;
                vertical-align: middle;
                width: 0.7rem;
            }}
            .calendar-dot:first-child {{
                margin-left: 0;
            }}
            .calendar-dot.green {{
                background: #22c55e;
            }}
            .calendar-dot.gray {{
                background: #6b7280;
            }}
        </style>
        <table class="ledger-calendar">
            <thead><tr>{weekday_headers}</tr></thead>
            <tbody>{''.join(html_rows)}</tbody>
        </table>
        <div class="calendar-legend">
            <span class="calendar-dot green"></span>Logged
            <span class="calendar-dot gray"></span>No data
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_analytics(title: str, blocks: pd.DataFrame, chart_key: str) -> None:
    st.subheader(title)
    totals = hours_by_category(blocks)

    if totals.empty:
        st.info("No categorized time blocks yet.")
        return

    st.dataframe(totals, hide_index=True, use_container_width=True)
    fig = px.bar(
        totals,
        x="category",
        y="hours",
        labels={"category": "Category", "hours": "Hours"},
        text_auto=".2f",
    )
    fig.update_layout(showlegend=False)
    st.plotly_chart(fig, use_container_width=True, key=chart_key)


def render_daily_tab(selected_day: date, categories: list[str]) -> None:
    st.header("Daily Grid")
    render_calendar(selected_day)
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


def render_week_tab(selected_day: date) -> None:
    st.header("Week View")
    days = week_dates(selected_day)
    blocks = get_blocks_for_dates(days)

    blocks["Time"] = blocks["start_time"] + " - " + blocks["end_time"]
    blocks["Day"] = pd.to_datetime(blocks["date"]).dt.strftime("%a %m/%d")

    week_grid = blocks.pivot(index="Time", columns="Day", values="category").reset_index()
    ordered_columns = ["Time"] + [day.strftime("%a %m/%d") for day in days]
    week_grid = week_grid.reindex(columns=ordered_columns)

    st.dataframe(week_grid, hide_index=True, use_container_width=True, height=720)


def render_analytics_tab(selected_day: date) -> None:
    st.header("Analytics")
    day_blocks = get_day_blocks(selected_day)
    week_blocks = get_blocks_for_dates(week_dates(selected_day))

    day_col, week_col = st.columns(2)
    with day_col:
        render_analytics("Selected Day", day_blocks, "selected_day_hours_chart")
    with week_col:
        render_analytics("Selected Week", week_blocks, "selected_week_hours_chart")


def main() -> None:
    st.title("Time Ledger")
    st.caption("Log your day in 15-minute blocks.")

    categories = get_categories()
    selected_day = query_param_date()
    previous_selected_day = st.session_state.get("selected_day")
    st.session_state["selected_day"] = selected_day
    if previous_selected_day != selected_day or "calendar_month" not in st.session_state:
        st.session_state["calendar_month"] = selected_day.replace(day=1)

    sidebar_day = st.sidebar.date_input(
        "Date",
        value=selected_day,
        key=f"sidebar_date_{selected_day.isoformat()}",
    )
    if sidebar_day != selected_day:
        set_selected_day(sidebar_day)
        st.rerun()

    daily_tab, week_tab, analytics_tab = st.tabs(["Daily", "Week", "Analytics"])

    with daily_tab:
        render_daily_tab(selected_day, categories)
    with week_tab:
        render_week_tab(selected_day)
    with analytics_tab:
        render_analytics_tab(selected_day)


if __name__ == "__main__":
    main()
