from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from comunicados.forms import TarefaInicialFormSet

from .forms import AcaoFormSet, AcaoFormularioForm, ResponderTarefaForm
from .models import StatusTarefa, Tarefa
from .services import responder_tarefa


@login_required
def minhas_tarefas_pendentes(request):
    tarefas = (
        Tarefa.objects.filter(status=StatusTarefa.PENDENTE)
        .filter(
            Q(responsavel=request.user)
            | Q(responsavel__isnull=True, departamento__responsaveis=request.user)
        )
        .select_related("comunicado", "departamento")
        .distinct()
        .order_by("prazo")
    )
    return render(request, "tarefas/minhas_pendentes.html", {"tarefas": tarefas})


@login_required
def nova_linha_acao(request):
    index = int(request.GET.get("index", 0))
    acao_form = AcaoFormularioForm(prefix=f"acoes-{index}")
    tarefa = get_object_or_404(Tarefa, pk=request.GET.get("tarefa"))
    return render(
        request,
        "tarefas/_acao_row_nova.html",
        {"acao_form": acao_form, "total_forms": index + 1, "departamento": tarefa.departamento},
    )


@login_required
def responder_tarefa_view(request, pk):
    tarefa = get_object_or_404(
        Tarefa.objects.select_related(
            "comunicado__departamento_solicitante", "comunicado__solicitante", "departamento"
        ),
        pk=pk,
    )

    if tarefa.status != StatusTarefa.PENDENTE:
        messages.error(request, "Essa Tarefa já foi respondida.")
        return redirect("comunicados:detalhe", pk=tarefa.comunicado_id)

    if request.method == "POST":
        form = ResponderTarefaForm(request.POST, request.FILES)
        acao_formset = AcaoFormSet(request.POST, prefix="acoes")
        escalonamento_formset = TarefaInicialFormSet(request.POST, prefix="escalonamento")

        if form.is_valid() and acao_formset.is_valid() and escalonamento_formset.is_valid():
            decisao = form.cleaned_data["decisao"]

            acoes_data = []
            if decisao == StatusTarefa.APROVADO_COM_ACOES:
                for acao_form in acao_formset:
                    descricao = acao_form.cleaned_data.get("descricao")
                    if not descricao:
                        continue
                    acoes_data.append(
                        {
                            "descricao": descricao,
                            "prazo_original": acao_form.cleaned_data["prazo_original"],
                            "responsavel": acao_form.cleaned_data.get("responsavel"),
                        }
                    )
                if not acoes_data:
                    form.add_error(
                        None, "Informe ao menos uma ação para 'Aprovado com ações'."
                    )

            novas_tarefas_data = []
            if form.cleaned_data.get("envolver_outro_departamento") == "SIM":
                for esc_form in escalonamento_formset:
                    departamento = esc_form.cleaned_data.get("departamento")
                    if not departamento:
                        continue
                    novas_tarefas_data.append(
                        {
                            "departamento": departamento,
                            "responsavel": esc_form.cleaned_data.get("responsavel_principal"),
                            "comentarios": esc_form.cleaned_data.get("comentarios", ""),
                        }
                    )
                if not novas_tarefas_data:
                    form.add_error(
                        None, "Adicione ao menos um departamento para envolver."
                    )

            if not form.errors:
                tarefa.justificativa = form.cleaned_data["justificativa"]
                tarefa.data_conclusao = timezone.localdate()
                responder_tarefa(
                    tarefa,
                    decisao,
                    acoes_data=acoes_data,
                    novas_tarefas_data=novas_tarefas_data,
                    anexos=form.cleaned_data.get("anexos"),
                )
                messages.success(request, "Resposta registrada.")
                return redirect("comunicados:detalhe", pk=tarefa.comunicado_id)
    else:
        form = ResponderTarefaForm()
        acao_formset = AcaoFormSet(prefix="acoes")
        escalonamento_formset = TarefaInicialFormSet(prefix="escalonamento")

    return render(
        request,
        "tarefas/form_responder.html",
        {
            "tarefa": tarefa,
            "comunicado": tarefa.comunicado,
            "form": form,
            "acao_formset": acao_formset,
            "escalonamento_formset": escalonamento_formset,
        },
    )
