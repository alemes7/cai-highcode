import datetime
from unittest.mock import patch

from django.test import TestCase

from core.models import Departamento
from tarefas.models import StatusTarefa, Tarefa

from .models import Comunicado, ContadorCaiFiscal, StatusComunicado, TipoComunicado
from .services import (
    atualizar_status_comunicado,
    calcular_ano_fiscal,
    calcular_status,
    criar_comunicado,
)


class CalcularStatusTests(TestCase):
    def setUp(self):
        self.departamento = Departamento.objects.create(nome="Qualidade")
        self.comunicado = Comunicado.objects.create(
            ano_fiscal="25'26",
            numero_sequencial=1,
            cai_fiscal="25'26-0001",
            data_criacao="2026-01-01",
            tipo=TipoComunicado.INTRODUCAO,
            departamento_solicitante=self.departamento,
            cliente="Cliente X",
        )

    def _criar_tarefa(self, status):
        return Tarefa.objects.create(
            comunicado=self.comunicado,
            departamento=self.departamento,
            status=status,
        )

    def test_sem_tarefas_fica_pendente(self):
        self.assertEqual(calcular_status(self.comunicado), StatusComunicado.PENDENTE)

    def test_alguma_pendente_mantem_pendente(self):
        self._criar_tarefa(StatusTarefa.APROVADO)
        self._criar_tarefa(StatusTarefa.PENDENTE)
        self.assertEqual(calcular_status(self.comunicado), StatusComunicado.PENDENTE)

    def test_todas_aprovadas_ou_nao_se_aplica_fica_aprovado(self):
        self._criar_tarefa(StatusTarefa.APROVADO)
        self._criar_tarefa(StatusTarefa.NAO_SE_APLICA)
        self.assertEqual(calcular_status(self.comunicado), StatusComunicado.APROVADO)

    def test_alguma_aprovado_com_acoes_prevalece_sobre_aprovado(self):
        self._criar_tarefa(StatusTarefa.APROVADO)
        self._criar_tarefa(StatusTarefa.NAO_SE_APLICA)
        self._criar_tarefa(StatusTarefa.APROVADO_COM_ACOES)
        self.assertEqual(
            calcular_status(self.comunicado), StatusComunicado.APROVADO_COM_ACOES
        )

    def test_aprovado_com_acoes_nao_prevalece_enquanto_houver_pendente(self):
        # Regressão: uma Tarefa escalonada (Pendente) não pode ser "engolida"
        # pela regra de Aprovado com ações — só decidimos o status final
        # quando não sobra nenhuma Tarefa pendente (assim como no fluxo real).
        self._criar_tarefa(StatusTarefa.APROVADO_COM_ACOES)
        self._criar_tarefa(StatusTarefa.PENDENTE)
        self.assertEqual(calcular_status(self.comunicado), StatusComunicado.PENDENTE)

    def test_rejeitado_tem_prioridade_maxima(self):
        self._criar_tarefa(StatusTarefa.APROVADO_COM_ACOES)
        self._criar_tarefa(StatusTarefa.REJEITADO)
        self._criar_tarefa(StatusTarefa.PENDENTE)
        self.assertEqual(calcular_status(self.comunicado), StatusComunicado.REJEITADO)

    def test_tarefa_cancelada_e_ignorada_no_calculo(self):
        self._criar_tarefa(StatusTarefa.APROVADO)
        self._criar_tarefa(StatusTarefa.CANCELADO)
        self.assertEqual(calcular_status(self.comunicado), StatusComunicado.APROVADO)

    def test_apenas_canceladas_fica_pendente(self):
        self._criar_tarefa(StatusTarefa.CANCELADO)
        self.assertEqual(calcular_status(self.comunicado), StatusComunicado.PENDENTE)


class AtualizarStatusComunicadoTests(TestCase):
    def setUp(self):
        self.departamento = Departamento.objects.create(nome="Qualidade")
        self.comunicado = Comunicado.objects.create(
            ano_fiscal="25'26",
            numero_sequencial=2,
            cai_fiscal="25'26-0002",
            data_criacao="2026-01-01",
            tipo=TipoComunicado.INTRODUCAO,
            departamento_solicitante=self.departamento,
            cliente="Cliente X",
        )

    def test_persiste_novo_status_e_retorna_true_quando_muda(self):
        Tarefa.objects.create(
            comunicado=self.comunicado,
            departamento=self.departamento,
            status=StatusTarefa.REJEITADO,
        )

        mudou = atualizar_status_comunicado(self.comunicado)

        self.comunicado.refresh_from_db()
        self.assertTrue(mudou)
        self.assertEqual(self.comunicado.status, StatusComunicado.REJEITADO)

    def test_retorna_false_quando_status_nao_muda(self):
        # Comunicado começa Pendente e não tem tarefas -> continua Pendente.
        mudou = atualizar_status_comunicado(self.comunicado)
        self.assertFalse(mudou)


class ComunicadoSignalsTests(TestCase):
    def setUp(self):
        self.departamento = Departamento.objects.create(nome="Qualidade")

    @patch("comunicados.signals.notificar_novo_comunicado.delay")
    def test_criar_comunicado_dispara_notificacao(self, mock_delay):
        with self.captureOnCommitCallbacks(execute=True):
            comunicado = Comunicado.objects.create(
                ano_fiscal="25'26",
                numero_sequencial=3,
                cai_fiscal="25'26-0003",
                data_criacao="2026-01-01",
                tipo=TipoComunicado.INTRODUCAO,
                departamento_solicitante=self.departamento,
                cliente="Cliente X",
            )
        mock_delay.assert_called_once_with(comunicado.pk)


class CalcularAnoFiscalTests(TestCase):
    def test_outubro_a_dezembro_inicia_ano_fiscal_no_ano_corrente(self):
        self.assertEqual(calcular_ano_fiscal(datetime.date(2026, 10, 1)), "26'27")
        self.assertEqual(calcular_ano_fiscal(datetime.date(2026, 12, 31)), "26'27")

    def test_janeiro_a_setembro_pertence_ao_ano_fiscal_anterior(self):
        self.assertEqual(calcular_ano_fiscal(datetime.date(2026, 1, 1)), "25'26")
        self.assertEqual(calcular_ano_fiscal(datetime.date(2026, 9, 30)), "25'26")


class CriarComunicadoTests(TestCase):
    def setUp(self):
        self.departamento = Departamento.objects.create(nome="Qualidade")
        self.qualidade = Departamento.objects.create(nome="Engenharia")

    def _dados_base(self, **overrides):
        dados = {
            "tipo": TipoComunicado.INTRODUCAO,
            "departamento_solicitante": self.departamento,
            "cliente": "Cliente X",
            "data_criacao": datetime.date(2026, 1, 15),
        }
        dados.update(overrides)
        return dados

    def test_gera_cai_fiscal_e_cria_tarefas(self):
        comunicado = criar_comunicado(
            self._dados_base(),
            [
                {"departamento": self.departamento},
                {"departamento": self.qualidade},
            ],
        )

        self.assertEqual(comunicado.ano_fiscal, "25'26")
        self.assertEqual(comunicado.numero_sequencial, 1)
        self.assertEqual(comunicado.cai_fiscal, "1 / 25'26")
        self.assertEqual(comunicado.tarefas.count(), 2)

    def test_sequencial_incrementa_dentro_do_mesmo_ano_fiscal(self):
        primeiro = criar_comunicado(self._dados_base(), [])
        segundo = criar_comunicado(self._dados_base(), [])

        self.assertEqual(primeiro.cai_fiscal, "1 / 25'26")
        self.assertEqual(segundo.cai_fiscal, "2 / 25'26")

    def test_sequencial_reseta_em_novo_ano_fiscal(self):
        criar_comunicado(self._dados_base(data_criacao=datetime.date(2026, 9, 30)), [])
        do_novo_ano = criar_comunicado(
            self._dados_base(data_criacao=datetime.date(2026, 10, 1)), []
        )

        self.assertEqual(do_novo_ano.ano_fiscal, "26'27")
        self.assertEqual(do_novo_ano.numero_sequencial, 1)
        self.assertEqual(do_novo_ano.cai_fiscal, "1 / 26'27")
        self.assertEqual(ContadorCaiFiscal.objects.count(), 2)
