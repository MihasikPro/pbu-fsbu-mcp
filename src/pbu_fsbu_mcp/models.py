"""Domain and response models for the PBU/FSBU corpus."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

StandardKind = Literal["ФСБУ", "ПБУ"]


class StandardStatus(str, Enum):
    ACTIVE = "действует"
    NOT_YET = "не вступил в силу"
    REPEALED = "утратил силу"


class Clause(BaseModel):
    edition_id: str
    standard_id: str
    path: str
    parent_path: str | None
    heading: str | None
    text: str

    @field_validator("text")
    @classmethod
    def _text_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("clause text must not be blank")
        return value

    @computed_field  # type: ignore[prop-decorator]
    @property
    def id(self) -> str:
        return f"{self.edition_id}#{self.path}"


class Edition(BaseModel):
    standard_id: str
    edition_no: int = Field(ge=1)
    amending_order: str | None
    effective_from: date
    clauses: list[Clause] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def id(self) -> str:
        return f"{self.standard_id}@{self.edition_no}"


class Standard(BaseModel):
    id: str
    kind: StandardKind
    number: str
    year: int
    title: str
    order_date: date
    order_no: str
    effective_from: date
    effective_to: date | None = None
    superseded_by: str | None = None
    source_url: str
    editions: list[Edition] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_period(self) -> Standard:
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be later than effective_from")
        return self

    def status_on(self, on_date: date) -> StandardStatus:
        # Imported here, not at module level, on purpose: `temporal` imports
        # StandardStatus from this module, so a top-level import would be circular.
        # The in-force rule lives in `temporal` alone - do not reimplement it here.
        from pbu_fsbu_mcp.temporal import status_on

        return status_on(self.effective_from, self.effective_to, on_date)


class StandardSummary(BaseModel):
    """One row of the registry returned by `list_standards`."""

    id: str
    kind: StandardKind
    number: str
    title: str
    order_date: date
    order_no: str
    effective_from: date
    effective_to: date | None
    status: StandardStatus
    superseded_by: str | None
    has_1c_mapping: bool
    source_url: str
    successors: list[str] = Field(default_factory=list)


class CrosslinkSource(BaseModel):
    """One standard-to-standard relation from `data/sources/crosslinks.yaml`."""

    from_standard: str
    to_standard: str
    kind: Literal["заменён", "аналог", "отсылка"]


class MappingSource(BaseModel):
    """One projection row as authored in a `data/sources/mappings/<config>/*.yaml` file.

    Keyed on `clause_path`, not a `clause.id` - see `schema.sql` on the `mapping`
    table for why. `edition_from` is the earliest edition (by `edition_no`) this
    row applies to; `None` means "since the standard's first edition".
    """

    clause_path: str
    kind: str
    object_ref: str
    note: str | None = None
    confidence: int = Field(ge=0, le=100)
    edition_from: int | None = None


class MappingFile(BaseModel):
    """One `data/sources/mappings/<config>/*.yaml` file."""

    standard_id: str
    config: str
    version_from: str | None = None
    mappings: list[MappingSource] = Field(default_factory=list)


class MappingEntry(BaseModel):
    """One projection row returned by `get_1c_mapping`.

    This is an interpretation of a clause, not the clause itself - it never
    carries clause text, on purpose. See `disclaimers.MAPPING_DISCLAIMER`.
    """

    clause_path: str
    kind: str
    object_ref: str
    presentation: str
    note: str | None
    confidence: int = Field(ge=0, le=100)


class ClauseResponse(BaseModel):
    """A single clause with full provenance."""

    standard_id: str
    standard_title: str
    path: str
    heading: str | None
    text: str
    parent_path: str | None
    parent_heading: str | None
    edition_no: int
    as_of_date: date
    status: StandardStatus
    order_ref: str
    source_url: str
    children: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SearchHit(BaseModel):
    standard_id: str
    standard_title: str
    path: str
    heading: str | None
    snippet: str
    score: float
    status: StandardStatus
