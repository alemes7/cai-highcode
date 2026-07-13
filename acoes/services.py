from django.utils import timezone

from .models import StatusAcao


def cancelar_acoes_pendentes_do_comunicado(comunicado):
    """Usada quando uma Tarefa é rejeitada: as Ações pendentes do Comunicado inteiro
    perdem o sentido, então são canceladas em bloco (update() evita N signals à toa)."""
    return comunicado.acoes.filter(status=StatusAcao.PENDENTE).update(
        status=StatusAcao.CANCELADO, data_conclusao=timezone.localdate()
    )


def cancelar_acao(acao):
    """Cancelamento manual de uma Ação isolada. Não afeta o status do Comunicado
    nem da Tarefa de origem — Ações nunca influenciam o status de ninguém
    (ver comunicados/services.py::calcular_status)."""
    acao.status = StatusAcao.CANCELADO
    acao.data_conclusao = timezone.localdate()
    acao.save(update_fields=["status", "data_conclusao", "atualizado_em"])
    return acao
