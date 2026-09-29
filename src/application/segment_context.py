from __future__ import annotations

SEGMENT_SCOPED_PREFIXES = (
    "segment_data:",
    "segment_filter:",
    "segment_period:",
    "segment_chart:",
)


def switch_segment_state(state: dict, segment_id: int) -> None:
    previous = state.get("active_segment_id")
    if previous == segment_id:
        return
    for key in list(state):
        if any(str(key).startswith(prefix) for prefix in SEGMENT_SCOPED_PREFIXES):
            state.pop(key, None)
    state["active_segment_id"] = segment_id
