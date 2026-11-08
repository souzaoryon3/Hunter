"""Validacao dos contratos de entrada."""

import re
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class DadosPessoais(BaseModel):
    nome: str = Field(min_length=2, max_length=255)
    email: str = Field(max_length=255)

    @field_validator("nome", "email", mode="before")
    @classmethod
    def limpar(cls, valor):
        return valor.strip() if isinstance(valor, str) else valor

    @field_validator("email")
    @classmethod
    def validar_email(cls, valor):
        if not re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", valor):
            raise ValueError("Informe um e-mail válido.")
        return valor


class Usuario(DadosPessoais):
    senha: str = Field(min_length=8, max_length=72)

    @field_validator("senha")
    @classmethod
    def validar_senha(cls, valor):
        if len(valor.encode("utf-8")) > 72:
            raise ValueError("A senha deve ter até 72 bytes.")
        return valor


class UsuarioUpdate(BaseModel):
    nome: Optional[str] = Field(None, min_length=2, max_length=255)
    email: Optional[str] = Field(None, max_length=255)
    senha: Optional[str] = Field(None, min_length=8, max_length=72)
    senha_atual: Optional[str] = None

    @field_validator("nome", "email", mode="before")
    @classmethod
    def limpar(cls, valor):
        return DadosPessoais.limpar(valor)

    @field_validator("email")
    @classmethod
    def validar_email(cls, valor):
        return DadosPessoais.validar_email(valor) if valor is not None else valor

    @field_validator("senha")
    @classmethod
    def validar_senha(cls, valor):
        return Usuario.validar_senha(valor) if valor is not None else valor


class Feedback(BaseModel):
    feedback: str = Field(min_length=1, max_length=5000)

    @field_validator("feedback", mode="before")
    @classmethod
    def limpar_mensagem(cls, valor):
        return valor.strip() if isinstance(valor, str) else valor


class FeedbackUpdate(Feedback):
    pass


class AlertaPreco(BaseModel):
    produto: str = Field(min_length=1, max_length=255)
    preco: float = Field(gt=0, le=1_000_000_000, allow_inf_nan=False)

    @field_validator("produto", mode="before")
    @classmethod
    def limpar_produto(cls, valor):
        return valor.strip() if isinstance(valor, str) else valor


class AlertaPrecoUpdate(BaseModel):
    produto: Optional[str] = Field(None, min_length=1, max_length=255)
    preco: Optional[float] = Field(None, gt=0, le=1_000_000_000, allow_inf_nan=False)

    @field_validator("produto", mode="before")
    @classmethod
    def limpar_produto(cls, valor):
        return AlertaPreco.limpar_produto(valor)
