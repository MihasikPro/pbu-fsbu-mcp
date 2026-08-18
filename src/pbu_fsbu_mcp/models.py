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


class MappingStatus(str, Enum):
    """Whether a standard has a 1C projection, and how trustworthy it is.

    Deliberately three states, not a bool: `NONE` and `DRAFT` both look like
    "no usable mapping yet" to a caller that only checks truthiness, which is
    exactly the confusion this type exists to prevent - `VERIFIED` is the only
    state where at least one row has been checked by a human against the
    clause text and the configuration (see `MappingSource.verified`).
    """

    NONE = "нет"
    DRAFT = "черновик"
    VERIFIED = "проверено"


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
    mapping_status: MappingStatus
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

    `verified` defaults to `False` and stays that way until a human reviewer
    edits the YAML by hand. Tooling that authors mapping rows (including AI
    drafting) must never set it to `True` - see `disclaimers.UNVERIFIED_MAPPING_WARNING`.
    """

    clause_path: str
    kind: str
    object_ref: str
    note: str | None = None
    confidence: int = Field(ge=0, le=100)
    edition_from: int | None = None
    verified: bool = False


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
    verified: bool


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


class ItsLinkSource(BaseModel):
    """One ИТС reference row as authored in a `data/sources/its/*.yaml` file.

    Only an identifier, a title, and a short summary in our own words are
    stored - never the article's own text, which is licensed 1C content.
    `summary` is capped at 400 characters as a technical guard against
    copy-pasting the source article, not a style preference.

    `verified` defaults to `False`, same rule and same reason as on
    `MappingSource.verified` - a human reviewer sets it, tooling never does.
    """

    clause_path: str
    its_id: str
    title: str
    summary: str = Field(max_length=400)
    verified: bool = False


class ItsLinkFile(BaseModel):
    """One `data/sources/its/*.yaml` file."""

    standard_id: str
    links: list[ItsLinkSource] = Field(default_factory=list)


class SearchHit(BaseModel):
    standard_id: str
    standard_title: str
    path: str
    heading: str | None
    snippet: str
    score: float
    status: StandardStatus
