from .models import StatusAcao


def cancelar_acoes_pendentes_do_comunicado(comunicado):
    """Usada quando uma Tarefa é rejeitada: as Ações pendentes do Comunicado inteiro
    perdem o sentido, então são canceladas em bloco (update() evita N signals à toa)."""
    return comunicado.acoes.filter(status=StatusAcao.PENDENTE).update(
        status=StatusAcao.CANCELADO
    )
