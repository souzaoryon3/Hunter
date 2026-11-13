-- Cadastro de varejistas para filtros e historico; nao altera dados existentes.
INSERT INTO hunter_catalog_shops(loja) VALUES
    ('TerabyteShop'),
    ('Amazon Brasil'),
    ('Magalu'),
    ('Fast Shop'),
    ('GK InfoStore'),
    ('Info Store')
ON CONFLICT (loja) DO NOTHING;
