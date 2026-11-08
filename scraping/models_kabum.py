from sqlalchemy import Column, Integer, String, Float
from sqlalchemy.ext.declarative import declarative_base

# Criando uma classe base para os modelos
Base = declarative_base()

class Produto(Base):
    __tablename__ = 'produtos_kabum'  # Nome da tabela no banco de dados

    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String, nullable=False)
    preco = Column(Float, nullable=False)  # Mudança de String para Float
    link = Column(String, nullable=False)  # URL do produto

    def __repr__(self):
        return f"<Produto(nome='{self.nome}', preco={self.preco}, link='{self.link}')>"
