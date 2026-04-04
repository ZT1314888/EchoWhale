from __future__ import annotations

from typing import Any, Generic, TypeVar

from fastapi import Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = Field(200, description="Business status code")
    message: str = Field("Success", description="Response message")
    data: T | None = Field(None, description="Response data")

    @staticmethod
    def success(
        data: Any = None,
        message: str = "Success",
        body_code: int = 200,
        http_code: int = status.HTTP_200_OK,
        headers: dict[str, str] | None = None,
    ) -> JSONResponse:
        return JSONResponse(
            content={
                "code": body_code,
                "message": message,
                "data": jsonable_encoder(data),
            },
            status_code=http_code,
            headers=headers,
        )

    @staticmethod
    def success_without_data(
        http_code: int = status.HTTP_204_NO_CONTENT,
        headers: dict[str, str] | None = None,
    ) -> Response:
        return Response(status_code=http_code, headers=headers)

    @staticmethod
    def failed(
        message: str,
        body_code: int,
        http_code: int = status.HTTP_400_BAD_REQUEST,
        data: Any = None,
        headers: dict[str, str] | None = None,
    ) -> JSONResponse:
        content: dict[str, Any] = {
            "code": body_code,
            "message": message,
        }
        if data is not None:
            content["data"] = jsonable_encoder(data)

        return JSONResponse(
            content=content,
            status_code=http_code,
            headers=headers,
        )
