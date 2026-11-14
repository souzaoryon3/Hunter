# Imagem base com Python 3.12
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Diretório de trabalho dentro do container
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 && rm -rf /var/lib/apt/lists/*

# Copia somente o requirements primeiro (melhora o cache)
COPY requirements.txt /app/

# Instala as dependências da aplicação
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Agora copia o restante do código
COPY . /app
RUN useradd --system --uid 10001 --create-home hunter && chown -R hunter:hunter /app
USER hunter

# Expõe a porta usada pelo Uvicorn/FastAPI
EXPOSE 8000

# Comando para iniciar a API quando o container rodar
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
