import pandas as pd


HOURS_PER_BLOCK = 0.25


def hours_by_category(blocks: pd.DataFrame) -> pd.DataFrame:
    if blocks.empty or "category" not in blocks.columns:
        return pd.DataFrame(columns=["category", "hours"])

    categorized = blocks.copy()
    categorized["category"] = categorized["category"].fillna("").astype(str).str.strip()
    categorized = categorized[categorized["category"] != ""]

    if categorized.empty:
        return pd.DataFrame(columns=["category", "hours"])

    totals = (
        categorized.groupby("category")
        .size()
        .mul(HOURS_PER_BLOCK)
        .reset_index(name="hours")
        .sort_values("hours", ascending=False)
    )
    return totals
