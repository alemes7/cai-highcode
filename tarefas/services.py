from django.db import transaction

from acoes.models import Acao

from .models import StatusTarefa, Tarefa


def responder_tarefa(tarefa, novo_status, *, acoes_data=None, novas_tarefas_data=None, anexos=None):
    """Processa a resposta a uma Tarefa: cria Tarefas de escalonamento, Ações
    (quando aplicável) e anexos, e só então atualiza o status da Tarefa original.

    Essa ordem é a parte importante: o recálculo do status do Comunicado
    (disparado pelo post_save de Tarefa em tarefas/signals.py) precisa
    enxergar, no mesmo momento, as Tarefas de escalonamento recém-criadas —
    senão o Comunicado pode fechar como Aprovado com uma Tarefa pendente
    "escondida" (era exatamente essa a race condition do Power Apps original,
    que consultava uma coleção local desatualizada).

    acoes_data: lista de dicts com os campos de Acao a criar (só usado quando
                novo_status == StatusTarefa.APROVADO_COM_ACOES).
    novas_tarefas_data: lista de dicts com os campos de cada Tarefa de
                        escalonamento — independem do novo_status escolhido.
    anexos: lista de UploadedFile (request.FILES), opcional.
    """
    from .models import TarefaAnexo

    with transaction.atomic():
        for dados_tarefa in novas_tarefas_data or []:
            Tarefa.objects.create(
                comunicado=tarefa.comunicado,
                tarefa_origem=tarefa,
                status=StatusTarefa.PENDENTE,
                **dados_tarefa,
            )

        if novo_status == StatusTarefa.APROVADO_COM_ACOES:
            for dados_acao in acoes_data or []:
                Acao.objects.create(
                    comunicado=tarefa.comunicado,
                    tarefa=tarefa,
                    **dados_acao,
                )

        for arquivo in anexos or []:
            TarefaAnexo.objects.create(
                tarefa=tarefa, arquivo=arquivo, nome_original=arquivo.name
            )

        tarefa.status = novo_status
        tarefa.save()

    return tarefa


def cancelar_tarefa(tarefa):
    """Cancelamento manual de uma Tarefa isolada (ex: departamento envolvido por
    engano) — ao contrário de responder_tarefa, não dispara escalonamento nem
    Ações. O recálculo do status do Comunicado roda normalmente via signal
    (tarefas/signals.py), e calcular_status já ignora Tarefas Canceladas."""
    tarefa.status = StatusTarefa.CANCELADO
    tarefa.save()
    return tarefa
