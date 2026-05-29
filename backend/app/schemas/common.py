from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict


T = TypeVar("T")


class SchemaModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ApiResponse(BaseModel, Generic[T]):
    success: bool
    data: T | None = None
    message: str | None = None


class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    error_code: str | None = None
    details: dict[str, Any] | None = None

