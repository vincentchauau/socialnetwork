from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Score = Annotated[int, Field(ge=0, le=100, strict=True)]


class MeasurementIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symmetry: Score
    eye: Score | None = None
    nose: Score | None = None
    mouth: Score | None = None
    ear: Score | None = None
    angle: Annotated[float, Field(ge=0, le=90, allow_inf_nan=False)] | None = None


class MeasurementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    created_at: datetime = Field(serialization_alias="createdAt")
    symmetry: int
    eye: int | None
    nose: int | None
    mouth: int | None
    ear: int | None
    angle: float | None
