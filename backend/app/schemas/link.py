import uuid

from pydantic import BaseModel


class LinkBatchCreate(BaseModel):
    raw_links: str
    apply_changes: bool = True


class LinkBatchResult(BaseModel):
    batch_id: uuid.UUID | None
    matched: int
    created: int
    unmatched: int
    duplicates: int
    details: list[dict]


class LinkValidationResult(BaseModel):
    total: int
    valid: int
    invalid: int
    details: list[dict]