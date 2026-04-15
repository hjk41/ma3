from app.core.ids import new_id
from app.core.time import utc_now_iso
from app.models.record import Record, RecordCreate, RecordUpdate
from app.models.enums import RecordStatus
from app.services.redaction import redact_value
from app.storage.repositories import RecordRepository


def create_record(payload: RecordCreate, library_id: str | None = None) -> Record:
    sanitized = RecordCreate.model_validate(redact_value(payload.model_dump()))
    now = utc_now_iso()
    record = Record(
        record_id=new_id("vk"),
        library_id=library_id,
        created_at=now,
        updated_at=now,
        **sanitized.model_dump(),
    )
    RecordRepository().insert(record)
    return record


def get_record(
    record_id: str,
    accessible_library_ids: set[str],
) -> Record | None:
    record = RecordRepository().get(record_id)
    if record is None:
        return None
    if record.library_id is None:
        return record
    if record.library_id in accessible_library_ids:
        return record
    return None


def update_record(
    record: Record,
    patch: RecordUpdate,
) -> Record:
    """Apply a partial update. Redacts free-text fields, bumps updated_at."""
    changes = {k: v for k, v in patch.model_dump().items() if v is not None}
    if not changes:
        return record
    # Redact any free-text fields in the patch
    text_fields = {"title", "summary", "claim"}
    for field in text_fields & changes.keys():
        changes[field] = redact_value(changes[field])
    changes["updated_at"] = utc_now_iso()
    updated = record.model_copy(update=changes)
    RecordRepository().insert(updated)
    return updated


def promote_record(
    record: Record,
    review_note: str | None = None,
) -> Record:
    if record.status != RecordStatus.draft:
        raise ValueError("only draft records can be promoted")
    now = utc_now_iso()
    updated = record.model_copy(update={
        "status": RecordStatus.active,
        "review_note": review_note,
        "reviewed_at": now,
        "updated_at": now,
    })
    RecordRepository().insert(updated)
    return updated


def reject_record(
    record: Record,
    review_note: str | None = None,
) -> Record:
    if record.status not in (RecordStatus.draft, RecordStatus.active):
        raise ValueError("only draft or active records can be rejected")
    now = utc_now_iso()
    updated = record.model_copy(update={
        "status": RecordStatus.invalid,
        "review_note": review_note,
        "reviewed_at": now,
        "updated_at": now,
    })
    RecordRepository().insert(updated)
    return updated
