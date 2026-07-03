from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render

from acoes.models import Acao, StatusAcao
from comunicados.models import Comunicado, StatusComunicado
from tarefas.models import StatusTarefa, Tarefa


@login_required
def inicio(request):
    comunicados_abertos = Comunicado.objects.filter(
        status__in=[StatusComunicado.PENDENTE, StatusComunicado.APROVADO_COM_ACOES]
    ).count()
    tarefas_abertas = Tarefa.objects.filter(status=StatusTarefa.PENDENTE).count()
    acoes_abertas = Acao.objects.filter(status=StatusAcao.PENDENTE).count()
    meus_comunicados = Comunicado.objects.filter(criado_por=request.user).count()
    minhas_tarefas_pendentes = (
        Tarefa.objects.filter(status=StatusTarefa.PENDENTE)
        .filter(
            Q(responsavel=request.user)
            | Q(responsavel__isnull=True, departamento__responsaveis=request.user)
        )
        .distinct()
        .count()
    )
    minhas_acoes_pendentes = Acao.objects.filter(
        status=StatusAcao.PENDENTE, responsavel=request.user
    ).count()

    return render(
        request,
        "core/inicio.html",
        {
            "comunicados_abertos": comunicados_abertos,
            "tarefas_abertas": tarefas_abertas,
            "acoes_abertas": acoes_abertas,
            "meus_comunicados": meus_comunicados,
            "minhas_tarefas_pendentes": minhas_tarefas_pendentes,
            "minhas_acoes_pendentes": minhas_acoes_pendentes,
        },
    )
