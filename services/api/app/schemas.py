from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=256)
    totp_code: str = Field(default="", max_length=12)


class LoginResponse(BaseModel):
    session_token: str
    expires_at: str
    owner_email: str


class ParagraphInput(BaseModel):
    id: str = Field(min_length=3, max_length=64)
    text: str = Field(min_length=1, max_length=40000)


class DocumentUpdateRequest(BaseModel):
    base_version_id: str = Field(min_length=3, max_length=64)
    paragraphs: list[ParagraphInput] = Field(min_length=1, max_length=400)


class RewriteSessionRequest(BaseModel):
    version_id: str = Field(min_length=3, max_length=64)


class RewriteMessageRequest(BaseModel):
    instruction: str = Field(min_length=2, max_length=1200)
    paragraph_id: str = Field(min_length=3, max_length=64)
    selected_text: str = Field(default="", max_length=10000)

    @field_validator("instruction")
    @classmethod
    def normalize_instruction(cls, value: str) -> str:
        return " ".join(value.split())


class PatchDecisionRequest(BaseModel):
    expected_base_version_id: str = Field(min_length=3, max_length=64)


class RestoreVersionRequest(BaseModel):
    expected_current_version_id: str = Field(min_length=3, max_length=64)


class JobEvent(BaseModel):
    id: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    result_ref: str | None = None
    error_code: str | None = None
