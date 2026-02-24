from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import date, datetime
import html


# ---------- Auth ----------

class LoginRequest(BaseModel):
    username: str
    password: str


# ---------- Farmaco ----------

class FarmacoCreate(BaseModel):
    nome: str = Field(..., max_length=100)
    descrizione: Optional[str] = Field(None, max_length=500)
    data_scadenza: Optional[date] = None

    @field_validator("nome")
    @classmethod
    def sanitize_nome(cls, v: str) -> str:
        return html.escape(v.strip())

    @field_validator("descrizione")
    @classmethod
    def sanitize_descrizione(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return html.escape(v.strip()) or None
        return v


class FarmacoUpdate(BaseModel):
    nome: Optional[str] = Field(None, max_length=100)
    descrizione: Optional[str] = Field(None, max_length=500)
    data_scadenza: Optional[date] = None
    stato: Optional[str] = None

    @field_validator("nome")
    @classmethod
    def sanitize_nome(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return html.escape(v.strip())
        return v

    @field_validator("descrizione")
    @classmethod
    def sanitize_descrizione(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return html.escape(v.strip()) or None
        return v

    @field_validator("stato")
    @classmethod
    def validate_stato(cls, v: Optional[str]) -> Optional[str]:
        allowed = {"attivo", "in_scadenza", "scaduto", "eliminato"}
        if v is not None and v not in allowed:
            raise ValueError(f"Stato deve essere uno di: {allowed}")
        return v


class FarmacoOut(BaseModel):
    id: int
    user_id: int
    nome: str
    descrizione: Optional[str]
    data_scadenza: Optional[date]
    stato: str
    notifica_scaduto_inviata: bool
    created_at: datetime
    deleted_at: Optional[datetime]
