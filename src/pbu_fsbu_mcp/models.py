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
        if on_date < self.effective_from:
            return StandardStatus.NOT_YET
        if self.effective_to is not None and on_date >= self.effective_to:
            return StandardStatus.REPEALED
        return StandardStatus.ACTIVE


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
    warnings: list[str] = Field(default_factory=list)


class SearchHit(BaseModel):
    standard_id: str
    standard_title: str
    path: str
    heading: str | None
    snippet: str
    score: float
