from datetime import date

from pydantic import BaseModel, field_validator, model_validator

from app.domain.calendar import resolve_iana_timezone


class CalendarPeriodRequest(BaseModel):
    """Inclusive local calendar period shared by history-based operations."""

    start_date: date
    end_date: date
    timezone: str

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        resolve_iana_timezone(value)
        return value

    @model_validator(mode="after")
    def validate_date_order(self) -> "CalendarPeriodRequest":
        if self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        if self.end_date == date.max:
            raise ValueError("end_date is outside the supported range")
        return self
