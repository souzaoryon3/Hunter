"""Evidencias ficticias somente em memoria; nenhum banco/site consultado."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest
from catalog_expansion.qualification import qualification_errors, campaign_summary


class QualificationTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        stamp = self.now-timedelta(minutes=1)
        self.context = dict(baseline_ids={1,2,3,4,5,6}, allowed_offers={"https://example.invalid/product"},
                            campaign_started_at=self.now-timedelta(hours=1), now=self.now)
        self.row = dict(produto_id=7,nome="FICTICIO Teste",marca="FICTICIA",modelo="Modelo teste",categoria="Teste",loja="Fixture",
                        link="https://example.invalid/product",imagem_url="https://example.invalid/model.jpg",preco="99.90",coletado_em=stamp,
                        historico=dict(observacao_id=1,produto_id=7,coletado_em=stamp),
                        evidencia_oferta=dict(url="https://example.invalid/product",http_status=200,coletado_em=stamp),
                        evidencia_identidade=dict(url="https://example.invalid/product",marca="FICTICIA",modelo="Modelo teste",categoria="Teste",
                                                 imagens_do_modelo=["https://example.invalid/model.jpg"],revisao_confirmada=True),
                        evidencia_frontend=dict(produto_id=7,current_src="https://example.invalid/model.jpg",complete=True,
                                                natural_width=600,verificado_em=self.now,busca=True,filtros=True,comparacao=True))

    def test_requires_all_evidence(self):
        self.assertEqual(qualification_errors(self.row,**self.context),[])
        row=deepcopy(self.row);row.pop("marca")
        self.assertIn("campo_ausente_marca",qualification_errors(row,**self.context))

    def test_existing_and_duplicate_products_do_not_count(self):
        row=deepcopy(self.row);row["produto_id"]=1
        self.assertEqual(campaign_summary([row],**self.context)["concluidos"],0)
        self.assertEqual(campaign_summary([self.row,self.row],**self.context)["concluidos"],1)

    def test_fallback_or_broken_image_rejected(self):
        for changes in ({"current_src":"http://localhost/fallback.svg"},{"natural_width":0},{"complete":False}):
            row=deepcopy(self.row);row["evidencia_frontend"].update(changes)
            self.assertIn("imagem_nao_validada_no_frontend",qualification_errors(row,**self.context))

    def test_wrong_model_and_unreviewed_image_rejected(self):
        row=deepcopy(self.row);row["evidencia_identidade"]["modelo"]="Outro modelo"
        self.assertIn("identidade_ou_imagem_do_modelo_nao_confirmada",qualification_errors(row,**self.context))

    def test_missing_history_or_cached_date_rejected(self):
        row=deepcopy(self.row);row["historico"]={}
        self.assertIn("historico_inicial_nao_comprovado",qualification_errors(row,**self.context))
        row=deepcopy(self.row);row["coletado_em"]=self.now-timedelta(days=2)
        self.assertIn("coleta_sem_data_valida_da_campanha",qualification_errors(row,**self.context))

    def test_missing_integration_or_unapproved_source_rejected(self):
        row=deepcopy(self.row);row["evidencia_frontend"]["comparacao"]=False
        self.assertIn("integracao_nao_validada_comparacao",qualification_errors(row,**self.context))
        context={**self.context,"allowed_offers":set()}
        self.assertIn("oferta_sem_url_permitida",qualification_errors(self.row,**context))
