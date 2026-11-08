-- Baseline para banco novo/isolado; banco principal existente NAO e alterado.

                CREATE TABLE IF NOT EXISTS usuarios (
                    id SERIAL PRIMARY KEY, nome VARCHAR(255) NOT NULL,
                    email VARCHAR(255) NOT NULL UNIQUE, senha VARCHAR(255) NOT NULL,
                    data_criacao TIMESTAMP DEFAULT now());
                CREATE TABLE IF NOT EXISTS alertas_preco (
                    id SERIAL PRIMARY KEY, usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
                    produto VARCHAR(255) NOT NULL, preco DOUBLE PRECISION NOT NULL CHECK(preco>0),
                    created_at TIMESTAMP DEFAULT now());
                CREATE TABLE IF NOT EXISTS feedbacks (
                    id SERIAL PRIMARY KEY, usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
                    nome VARCHAR(255), email VARCHAR(255), feedback TEXT NOT NULL, data_envio TIMESTAMP DEFAULT now());
                CREATE TABLE IF NOT EXISTS produtos_kabum (id SERIAL PRIMARY KEY, nome VARCHAR(255), preco DOUBLE PRECISION, link TEXT);
                CREATE TABLE IF NOT EXISTS produtos_mercadolivre (id SERIAL PRIMARY KEY, nome VARCHAR(255), preco DOUBLE PRECISION, link TEXT);
            