from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from comunicados.models import Comunicado, TipoComunicado
from core.models import Departamento
from tarefas.models import Tarefa

from .models import Acao
from .tasks import verificar_prazos_acoes

User = get_user_model()


class AcaoSignalsTests(TestCase):
    def setUp(self):
        self.responsavel = User.objects.create_user(
            username="resp", email="resp@example.com"
        )
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
        self.tarefa = Tarefa.objects.create(
            comunicado=self.comunicado, departamento=self.departamento
        )

    @patch("acoes.signals.notificar_nova_acao.delay")
    def test_criar_acao_dispara_notificacao(self, mock_delay):
        with self.captureOnCommitCallbacks(execute=True):
            acao = Acao.objects.create(
                comunicado=self.comunicado,
                tarefa=self.tarefa,
                descricao="Ação de teste",
                prazo_original="2026-02-01",
                responsavel=self.responsavel,
            )
        mock_delay.assert_called_once_with(acao.pk)

    def test_acao_herda_departamento_da_tarefa(self):
        acao = Acao.objects.create(
            comunicado=self.comunicado,
            tarefa=self.tarefa,
            descricao="Ação de teste",
            prazo_original="2026-02-01",
        )
        self.assertEqual(acao.departamento_id, self.tarefa.departamento_id)


class VerificarPrazosAcoesTests(TestCase):
    def setUp(self):
        self.responsavel = User.objects.create_user(
            username="resp", email="resp@example.com"
        )
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
        self.tarefa = Tarefa.objects.create(
            comunicado=self.comunicado, departamento=self.departamento
        )
        self.hoje = timezone.localdate()

    def _criar_acao(self, prazo_original, prazo_reajustado=None):
        return Acao.objects.create(
            comunicado=self.comunicado,
            tarefa=self.tarefa,
            descricao="Ação de teste",
            prazo_original=prazo_original,
            prazo_reajustado=prazo_reajustado,
            responsavel=self.responsavel,
        )

    @patch("acoes.tasks.enviar_email")
    def test_ignora_acao_com_prazo_distante(self, mock_enviar):
        self._criar_acao(self.hoje + timedelta(days=10))
        verificar_prazos_acoes()
        mock_enviar.assert_not_called()

    @patch("acoes.tasks.enviar_email")
    def test_notifica_acao_proxima_do_prazo(self, mock_enviar):
        self._criar_acao(self.hoje + timedelta(days=3))
        verificar_prazos_acoes()
        mock_enviar.assert_called_once()

    @patch("acoes.tasks.enviar_email")
    def test_notifica_acao_atrasada(self, mock_enviar):
        self._criar_acao(self.hoje - timedelta(days=2))
        verificar_prazos_acoes()
        mock_enviar.assert_called_once()

    @patch("acoes.tasks.enviar_email")
    def test_prazo_reajustado_prevalece_sobre_original(self, mock_enviar):
        # Original está distante, mas o reajustado está vencido -> deve notificar.
        self._criar_acao(
            self.hoje + timedelta(days=30), prazo_reajustado=self.hoje - timedelta(days=1)
        )
        verificar_prazos_acoes()
        mock_enviar.assert_called_once()
