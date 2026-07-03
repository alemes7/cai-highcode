from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from acoes.models import Acao, StatusAcao
from comunicados.models import Comunicado, StatusComunicado, TipoComunicado
from core.models import Departamento

from .models import StatusTarefa, Tarefa
from .services import responder_tarefa

User = get_user_model()


class TarefaSignalsTests(TestCase):
    def setUp(self):
        self.solicitante = User.objects.create_user(
            username="solicitante", email="solicitante@example.com"
        )
        self.departamento = Departamento.objects.create(nome="Qualidade")
        self.outro_departamento = Departamento.objects.create(nome="Engenharia")
        self.comunicado = Comunicado.objects.create(
            ano_fiscal="25'26",
            numero_sequencial=1,
            cai_fiscal="25'26-0001",
            data_criacao="2026-01-01",
            tipo=TipoComunicado.INTRODUCAO,
            departamento_solicitante=self.departamento,
            solicitante=self.solicitante,
            cliente="Cliente X",
        )

    @patch("tarefas.signals.notificar_nova_tarefa.delay")
    def test_criar_tarefa_dispara_notificacao(self, mock_delay):
        with self.captureOnCommitCallbacks(execute=True):
            tarefa = Tarefa.objects.create(
                comunicado=self.comunicado, departamento=self.departamento
            )
        mock_delay.assert_called_once_with(tarefa.pk)

    @patch("tarefas.signals.notificar_comunicado_finalizado.delay")
    @patch("tarefas.signals.notificar_tarefa_rejeitada.delay")
    def test_rejeitar_tarefa_rejeita_comunicado_e_cancela_acoes_pendentes(
        self, mock_rejeitada, mock_finalizado
    ):
        tarefa = Tarefa.objects.create(
            comunicado=self.comunicado, departamento=self.departamento
        )
        acao_pendente = Acao.objects.create(
            comunicado=self.comunicado,
            tarefa=tarefa,
            descricao="Ação pendente",
            prazo_original="2026-02-01",
        )

        with self.captureOnCommitCallbacks(execute=True):
            tarefa.status = StatusTarefa.REJEITADO
            tarefa.save()

        self.comunicado.refresh_from_db()
        acao_pendente.refresh_from_db()

        self.assertEqual(self.comunicado.status, StatusComunicado.REJEITADO)
        self.assertEqual(acao_pendente.status, StatusAcao.CANCELADO)
        mock_rejeitada.assert_called_once_with(tarefa.pk)
        mock_finalizado.assert_called_once_with(self.comunicado.pk)

    @patch("tarefas.signals.notificar_comunicado_finalizado.delay")
    def test_comunicado_so_finaliza_quando_ultima_tarefa_responde(self, mock_finalizado):
        tarefa_1 = Tarefa.objects.create(
            comunicado=self.comunicado, departamento=self.departamento
        )
        tarefa_2 = Tarefa.objects.create(
            comunicado=self.comunicado, departamento=self.outro_departamento
        )

        with self.captureOnCommitCallbacks(execute=True):
            tarefa_1.status = StatusTarefa.APROVADO
            tarefa_1.save()

        self.comunicado.refresh_from_db()
        self.assertEqual(self.comunicado.status, StatusComunicado.PENDENTE)
        mock_finalizado.assert_not_called()

        with self.captureOnCommitCallbacks(execute=True):
            tarefa_2.status = StatusTarefa.APROVADO
            tarefa_2.save()

        self.comunicado.refresh_from_db()
        self.assertEqual(self.comunicado.status, StatusComunicado.APROVADO)
        mock_finalizado.assert_called_once_with(self.comunicado.pk)

    @patch("tarefas.signals.notificar_tarefa_rejeitada.delay")
    @patch("tarefas.signals.notificar_comunicado_finalizado.delay")
    def test_salvar_sem_mudar_status_nao_dispara_nada(self, mock_finalizado, mock_rejeitada):
        tarefa = Tarefa.objects.create(
            comunicado=self.comunicado, departamento=self.departamento
        )

        with self.captureOnCommitCallbacks(execute=True):
            tarefa.comentarios = "apenas um comentário"
            tarefa.save()

        mock_finalizado.assert_not_called()
        mock_rejeitada.assert_not_called()


class ResponderTarefaTests(TestCase):
    """Cobre o escalonamento (Tarefa gerando outra Tarefa) revelado pelo fluxo real
    do Power Apps: precisa acontecer ANTES do recálculo do status do Comunicado,
    senão o Comunicado pode fechar como Aprovado com uma Tarefa pendente escondida."""

    def setUp(self):
        self.departamento = Departamento.objects.create(nome="Qualidade")
        self.outro_departamento = Departamento.objects.create(nome="Engenharia")
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

    def test_aprovar_com_escalonamento_mantem_comunicado_pendente(self):
        responder_tarefa(
            self.tarefa,
            StatusTarefa.APROVADO,
            novas_tarefas_data=[{"departamento": self.outro_departamento}],
        )

        self.comunicado.refresh_from_db()
        self.assertEqual(self.comunicado.status, StatusComunicado.PENDENTE)
        self.assertEqual(self.comunicado.tarefas.count(), 2)

        nova_tarefa = self.comunicado.tarefas.get(departamento=self.outro_departamento)
        self.assertEqual(nova_tarefa.status, StatusTarefa.PENDENTE)
        self.assertEqual(nova_tarefa.tarefa_origem_id, self.tarefa.pk)

    def test_aprovar_com_acoes_e_escalonamento_nao_finaliza_comunicado(self):
        # Regressão pega em teste manual: "Aprovado com ações" não pode
        # vencer a Tarefa de escalonamento que acabou de nascer Pendente.
        responder_tarefa(
            self.tarefa,
            StatusTarefa.APROVADO_COM_ACOES,
            acoes_data=[
                {"descricao": "Revisar documento", "prazo_original": "2026-03-01"},
            ],
            novas_tarefas_data=[{"departamento": self.outro_departamento}],
        )

        self.comunicado.refresh_from_db()
        self.assertEqual(self.comunicado.status, StatusComunicado.PENDENTE)

    def test_aprovar_com_acoes_cria_acoes_vinculadas(self):
        responder_tarefa(
            self.tarefa,
            StatusTarefa.APROVADO_COM_ACOES,
            acoes_data=[
                {"descricao": "Revisar documento", "prazo_original": "2026-03-01"},
            ],
        )

        self.assertEqual(self.tarefa.acoes.count(), 1)
        self.comunicado.refresh_from_db()
        self.assertEqual(self.comunicado.status, StatusComunicado.APROVADO_COM_ACOES)

    def test_aprovar_sem_escalonamento_finaliza_comunicado_normalmente(self):
        responder_tarefa(self.tarefa, StatusTarefa.APROVADO)

        self.comunicado.refresh_from_db()
        self.assertEqual(self.comunicado.status, StatusComunicado.APROVADO)
