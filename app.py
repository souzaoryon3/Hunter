"""Entrada compativel: uvicorn app:app. Implementacao em backend/."""
from backend.main import app, create_app
from backend.database import get_db
from backend.schemas import (DadosPessoais, Usuario, UsuarioUpdate, Feedback,
    FeedbackUpdate, AlertaPreco, AlertaPrecoUpdate)
