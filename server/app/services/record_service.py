from app.core.ids import new_id
from app.core.time import utc_now_iso
from app.models.record import Record, RecordCreate, RecordUpdate
from app.models.enums import RecordStatus, RelationType
from app.models.relation import RecordRelation
from app.services.op_log_service import write_op_log
from app.services.redaction import redact_value
from app.storage.repositories import RecordRepository, RelationRepository


def create_record(
    payload: RecordCreate,
    library_id: str | None = None,
    redaction_mode: str = "auto",
) -> Record:
    sanitized = RecordCreate.model_validate(redact_value(payload.model_dump(), mode=redaction_mode))
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


def delete_record(record_id: str) -> bool:
    return RecordRepository().delete(record_id)


# ── Curation lifecycle transitions ────────────────────────────────────────────
# These power the "knowledge staleness" curation flow. Status changes are soft
# (the record is never deleted) so they stay auditable and reversible, and each
# transition emits an op_log event for the audit trail.


def mark_record_stale(record: Record, review_note: str | None = None) -> Record:
    """Flag a record as outdated. Stays searchable but soft-decayed in ranking."""
    if record.status not in (RecordStatus.active, RecordStatus.superseded):
        raise ValueError("only active or superseded records can be marked stale")
    now = utc_now_iso()
    updated = record.model_copy(update={
        "status": RecordStatus.stale,
        "review_note": review_note,
        "reviewed_at": now,
        "updated_at": now,
    })
    RecordRepository().insert(updated)
    write_op_log(
        "curation_mark_stale",
        record_id=record.record_id,
        library_id=record.library_id,
        review_note=review_note,
    )
    return updated


def supersede_record(
    record: Record,
    superseded_by: str,
    review_note: str | None = None,
) -> tuple[Record, RecordRelation]:
    """Mark ``record`` as superseded by a newer record and link them.

    Creates a ``supersedes`` relation (newer -> older) so the replacement chain
    is traceable, and soft-decays the old record in search rather than deleting it.
    """
    if record.status not in (RecordStatus.active, RecordStatus.stale):
        raise ValueError("only active or stale records can be superseded")
    if superseded_by == record.record_id:
        raise ValueError("a record cannot supersede itself")
    repo = RecordRepository()
    newer = repo.get(superseded_by)
    if newer is None:
        raise ValueError("superseded_by record not found")

    now = utc_now_iso()
    updated = record.model_copy(update={
        "status": RecordStatus.superseded,
        "review_note": review_note,
        "reviewed_at": now,
        "updated_at": now,
    })
    repo.insert(updated)

    relation = RecordRelation(
        relation_id=new_id("rel"),
        from_record_id=superseded_by,
        to_record_id=record.record_id,
        relation_type=RelationType.supersedes,
        summary=review_note,
        created_at=now,
    )
    RelationRepository().insert(relation)

    write_op_log(
        "curation_supersede",
        record_id=record.record_id,
        superseded_by=superseded_by,
        relation_id=relation.relation_id,
        library_id=record.library_id,
        review_note=review_note,
    )
    return updated, relation


def restore_record(record: Record, review_note: str | None = None) -> Record:
    """Reverse a stale/superseded marking, bringing a record back to active."""
    if record.status not in (RecordStatus.stale, RecordStatus.superseded):
        raise ValueError("only stale or superseded records can be restored")
    now = utc_now_iso()
    updated = record.model_copy(update={
        "status": RecordStatus.active,
        "review_note": review_note,
        "reviewed_at": now,
        "updated_at": now,
    })
    RecordRepository().insert(updated)
    write_op_log(
        "curation_restore",
        record_id=record.record_id,
        library_id=record.library_id,
        review_note=review_note,
    )
    return updated
