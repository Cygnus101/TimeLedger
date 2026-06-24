from datetime import date, datetime, time, timedelta


SLOT_MINUTES = 15
SLOTS_PER_DAY = 24 * 60 // SLOT_MINUTES


def generate_time_slots() -> list[dict]:
    """Return the 96 fixed 15-minute slots in a day."""
    slots = []
    day_start = datetime.combine(date.today(), time.min)

    for slot_index in range(SLOTS_PER_DAY):
        start_dt = day_start + timedelta(minutes=slot_index * SLOT_MINUTES)
        end_dt = start_dt + timedelta(minutes=SLOT_MINUTES)
        slots.append(
            {
                "slot_index": slot_index,
                "start_time": start_dt.strftime("%H:%M"),
                "end_time": end_dt.strftime("%H:%M"),
                "time_label": f"{start_dt:%H:%M} - {end_dt:%H:%M}",
            }
        )

    return slots


def date_to_text(value: date) -> str:
    return value.strftime("%Y-%m-%d")


def week_start_for(value: date) -> date:
    return value - timedelta(days=value.weekday())


def week_dates(value: date) -> list[date]:
    start = week_start_for(value)
    return [start + timedelta(days=offset) for offset in range(7)]


def time_options() -> list[str]:
    return [slot["start_time"] for slot in generate_time_slots()] + ["24:00"]


def slot_index_for_time(value: str) -> int:
    if value == "24:00":
        return SLOTS_PER_DAY

    parsed = datetime.strptime(value, "%H:%M").time()
    total_minutes = parsed.hour * 60 + parsed.minute

    if total_minutes % SLOT_MINUTES != 0:
        raise ValueError("Time must align to a 15-minute boundary.")

    return total_minutes // SLOT_MINUTES
