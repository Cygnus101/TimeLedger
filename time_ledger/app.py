"""
Run locally:
    pip install -r requirements.txt
    streamlit run app.py
"""

from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics import hours_by_category
from database import (
    fill_time_range,
    get_blocks_for_dates,
    get_categories,
    get_day_blocks,
    initialize_database,
    update_day_blocks,
)
from utils import slot_index_for_time, time_options, week_dates


st.set_page_config(page_title="Time Ledger", layout="wide")

initialize_database()


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

    with st.form("fill_range_form", clear_on_submit=False):
        st.subheader("Fill Range")
        col1, col2, col3, col4 = st.columns([1, 1, 1, 2])
        options = time_options()

        with col1:
            start_time = st.selectbox("Start time", options[:-1], index=32)
        with col2:
            end_time = st.selectbox("End time", options[1:], index=39)
        with col3:
            range_category = st.selectbox("Category", categories)
        with col4:
            range_note = st.text_input("Note")

        submitted = st.form_submit_button("Fill selected range")

    if submitted:
        start_slot = slot_index_for_time(start_time)
        end_slot = slot_index_for_time(end_time)

        if end_slot <= start_slot:
            st.error("End time must be after start time.")
        else:
            fill_time_range(selected_day, start_slot, end_slot, range_category, range_note)
            st.success("Time range updated.")
            st.rerun()

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
    selected_day = st.sidebar.date_input("Date", value=date.today())

    daily_tab, week_tab, analytics_tab = st.tabs(["Daily", "Week", "Analytics"])

    with daily_tab:
        render_daily_tab(selected_day, categories)
    with week_tab:
        render_week_tab(selected_day)
    with analytics_tab:
        render_analytics_tab(selected_day)


if __name__ == "__main__":
    main()
