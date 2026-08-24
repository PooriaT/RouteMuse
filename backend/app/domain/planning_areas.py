from pydantic import BaseModel, Field, model_validator


class BoundingBox(BaseModel):
    """Provider-neutral geographic bounds in WGS84 degrees."""

    south: float = Field(ge=-90, le=90)
    west: float = Field(ge=-180, le=180)
    north: float = Field(ge=-90, le=90)
    east: float = Field(ge=-180, le=180)

    @model_validator(mode="after")
    def validate_order(self) -> "BoundingBox":
        if self.south > self.north:
            raise ValueError("south must be less than or equal to north")
        return self


class PlanningArea(BaseModel):
    """A location selected for planning, independent of geocoding providers."""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    display_name: str = Field(min_length=1)
    bounding_box: BoundingBox | None = None
    source_provider: str = Field(min_length=1)
    source_attribution: str = Field(min_length=1)
