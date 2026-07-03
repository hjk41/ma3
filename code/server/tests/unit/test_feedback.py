from __future__ import annotations

from app.storage.db import (
    clear_record_feedback,
    get_feedback_summaries,
    initialize_database,
    insert_record,
    set_record_feedback,
)


def test_record_feedback_upsert_and_clear():
    initialize_database()
    row = insert_record(
        library_id="lib_default",
        case_id=None,
        status="active",
        problem="feedback unit test",
        outcome="resolved",
        result_summary="ok",
        payload={"problem": "feedback unit test"},
    )
    record_id = row["record_id"]
    set_record_feedback(record_id, "user:a", 1)
    set_record_feedback(record_id, "user:b", -1)
    set_record_feedback(record_id, "user:a", -1)

    summary = get_feedback_summaries([record_id], principal_id="user:a")[record_id]
    assert summary == {"up": 0, "down": 2, "my_vote": "down"}

    clear_record_feedback(record_id, "user:a")
    summary = get_feedback_summaries([record_id], principal_id="user:a")[record_id]
    assert summary == {"up": 0, "down": 1}
