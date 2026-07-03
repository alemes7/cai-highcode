from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ConcluirAcaoForm
from .models import Acao, AcaoAnexo, StatusAcao


@login_required
def minhas_acoes_pendentes(request):
    acoes = (
        Acao.objects.filter(status=StatusAcao.PENDENTE, responsavel=request.user)
        .select_related("comunicado", "tarefa")
        .order_by("prazo_original")
    )
    return render(request, "acoes/minhas_pendentes.html", {"acoes": acoes})


@login_required
def concluir_acao_view(request, pk):
    acao = get_object_or_404(
        Acao.objects.select_related(
            "comunicado__departamento_solicitante",
            "comunicado__solicitante",
            "tarefa",
            "departamento",
            "responsavel",
        ).prefetch_related("anexos"),
        pk=pk,
    )

    if acao.status != StatusAcao.PENDENTE:
        messages.error(request, "Essa Ação já foi encerrada.")
        return redirect("comunicados:detalhe", pk=acao.comunicado_id)

    if request.method == "POST":
        form = ConcluirAcaoForm(request.POST, request.FILES)
        if form.is_valid():
            novo_status = form.cleaned_data["status"]
            # Prazo reajustado só pode ser alterado enquanto a Ação continua
            # Pendente — ao concluir/cancelar, o campo fica travado na tela,
            # e aqui garantimos isso de novo no servidor (um input disabled
            # simplesmente não é enviado no POST, então não dá pra confiar só
            # no JS: se não fizer essa checagem, o valor existente seria
            # apagado sempre que o campo viesse ausente do formulário).
            if novo_status == StatusAcao.PENDENTE:
                acao.prazo_reajustado = form.cleaned_data.get("prazo_reajustado")
            acao.status = novo_status
            acao.observacoes = form.cleaned_data["observacoes"]
            acao.save(
                update_fields=["status", "prazo_reajustado", "observacoes", "atualizado_em"]
            )
            for arquivo in form.cleaned_data.get("anexos") or []:
                AcaoAnexo.objects.create(
                    acao=acao, arquivo=arquivo, nome_original=arquivo.name
                )
            messages.success(request, "Ação atualizada.")
            return redirect("comunicados:detalhe", pk=acao.comunicado_id)
    else:
        form = ConcluirAcaoForm(
            initial={
                "status": acao.status,
                "prazo_reajustado": acao.prazo_reajustado,
                "observacoes": acao.observacoes,
            }
        )

    return render(request, "acoes/form_concluir.html", {"acao": acao, "form": form})
