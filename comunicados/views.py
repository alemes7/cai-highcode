from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from core.models import Departamento

from .forms import ComunicadoForm, TarefaInicialForm, TarefaInicialFormSet
from .models import Comunicado, StatusComunicado
from .services import cancelar_comunicado, criar_comunicado


@login_required
def novo_comunicado(request):
    if request.method == "POST":
        form = ComunicadoForm(request.POST, request.FILES)
        tarefa_formset = TarefaInicialFormSet(request.POST, prefix="tarefas")

        if form.is_valid() and tarefa_formset.is_valid():
            tarefas_data = []
            for tarefa_form in tarefa_formset:
                departamento = tarefa_form.cleaned_data.get("departamento")
                if not departamento:
                    continue
                tarefas_data.append(
                    {
                        "departamento": departamento,
                        "responsavel": tarefa_form.cleaned_data.get("responsavel_principal"),
                        "comentarios": tarefa_form.cleaned_data.get("comentarios", ""),
                    }
                )

            if not tarefas_data:
                form.add_error(None, "Adicione ao menos um departamento na lista de Tarefas.")
            else:
                dados_comunicado = {
                    "tipo": form.cleaned_data["tipo"],
                    "departamento_solicitante": form.cleaned_data["departamento_solicitante"],
                    "solicitante": form.cleaned_data["solicitante"],
                    "criado_por": request.user,
                    "cliente": form.cleaned_data["cliente"],
                    "numero_projeto": form.cleaned_data["numero_projeto"],
                    "data_cai": form.cleaned_data["data_cai"],
                    "revisao": form.cleaned_data["revisao"],
                    "comentarios": form.cleaned_data["comentarios"],
                    "cancela_comunicado": form.cleaned_data.get("cancela_comunicado"),
                }
                comunicado = criar_comunicado(
                    dados_comunicado, tarefas_data, anexos=form.cleaned_data.get("anexos")
                )
                messages.success(request, f"Comunicado {comunicado.cai_fiscal} criado.")
                return redirect("comunicados:detalhe", pk=comunicado.pk)
    else:
        form = ComunicadoForm()
        tarefa_formset = TarefaInicialFormSet(prefix="tarefas")

    return render(
        request,
        "comunicados/form_novo.html",
        {"form": form, "tarefa_formset": tarefa_formset},
    )


@login_required
def nova_linha_tarefa(request):
    """Endpoint HTMX do botão "+ Adicionar Tarefa/Departamento": devolve uma
    linha nova do formset (fora dos índices já usados, mesmo que linhas do
    meio tenham sido removidas na tela — ver comentário no template).

    Reaproveitado também pelo escalonamento no Form2Tarefas (tarefas app):
    o prefixo do formset varia ("tarefas" no Novo Comunicado, "escalonamento"
    ao responder uma Tarefa), então vem por query param.
    """
    index = int(request.GET.get("index", 0))
    prefix = request.GET.get("prefix", "tarefas")
    tarefa_form = TarefaInicialForm(prefix=f"{prefix}-{index}")
    return render(
        request,
        "comunicados/_tarefa_row_nova.html",
        {"tarefa_form": tarefa_form, "total_forms": index + 1, "prefix": prefix},
    )


@login_required
def info_departamento(request):
    """Endpoint HTMX disparado ao trocar o Departamento de uma linha de Tarefa:
    mostra os Responsáveis/Responsáveis em cópia daquele departamento."""
    departamento_id = next(
        (v for k, v in request.GET.items() if k.endswith("-departamento") and v), None
    )
    departamento = None
    if departamento_id:
        departamento = Departamento.objects.filter(pk=departamento_id).first()
    return render(
        request, "comunicados/_info_departamento.html", {"departamento": departamento}
    )


@login_required
def detalhe_comunicado(request, pk):
    comunicado = get_object_or_404(
        Comunicado.objects.select_related("departamento_solicitante", "solicitante").prefetch_related(
            "anexos"
        ),
        pk=pk,
    )
    tarefas = comunicado.tarefas.select_related("departamento", "responsavel").order_by(
        "criado_em"
    )
    acoes = comunicado.acoes.select_related("departamento", "responsavel", "tarefa").order_by(
        "prazo_original"
    )
    return render(
        request,
        "comunicados/detalhe.html",
        {"comunicado": comunicado, "tarefas": tarefas, "acoes": acoes},
    )


@login_required
def meus_comunicados(request):
    comunicados = (
        Comunicado.objects.filter(criado_por=request.user)
        .select_related("departamento_solicitante")
        .order_by("-data_criacao")
    )
    return render(request, "comunicados/meus.html", {"comunicados": comunicados})


@login_required
def listar_abertos(request):
    comunicados = Comunicado.objects.select_related(
        "departamento_solicitante", "solicitante"
    ).order_by("-numero_sequencial")

    status = request.GET.get("status", "")
    cliente = request.GET.get("cliente", "")
    if status:
        comunicados = comunicados.filter(status=status)
    if cliente:
        comunicados = comunicados.filter(cliente__icontains=cliente)

    paginator = Paginator(comunicados, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "comunicados/lista_abertos.html",
        {
            "page_obj": page_obj,
            "status_choices": StatusComunicado.choices,
            "status_selecionado": status,
            "cliente_buscado": cliente,
        },
    )


@login_required
def cancelar_comunicado_view(request, pk):
    comunicado = get_object_or_404(Comunicado, pk=pk)
    if request.method == "POST":
        if comunicado.status == StatusComunicado.PENDENTE:
            cancelar_comunicado(comunicado)
            messages.success(request, f"Comunicado {comunicado.cai_fiscal} cancelado.")
        else:
            messages.error(request, "Esse Comunicado não pode mais ser cancelado.")
    return redirect("comunicados:listar_abertos")
