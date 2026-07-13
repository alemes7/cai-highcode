from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from comunicados.forms import TarefaInicialFormSet
from core.models import Departamento

from .forms import AcaoFormSet, AcaoFormularioForm, ResponderTarefaForm
from .models import StatusTarefa, Tarefa
from .services import cancelar_tarefa, responder_tarefa

User = get_user_model()

# Chave do filtro/ordenação (GET) -> campo(s) no model, para as telas de Tarefas.
# "cai" é composto: numero_sequencial sozinho reinicia a cada ano fiscal, então
# "137 / 23'24" apareceria antes de "5 / 25'26" se ordenássemos só por ele.
SORT_CAMPOS = {
    "cai": ["comunicado__ano_fiscal", "comunicado__numero_sequencial"],
    "departamento": ["departamento__nome"],
    "cliente": ["comunicado__cliente"],
    "projeto": ["comunicado__numero_projeto"],
    "responsavel": ["responsavel__first_name"],
    "status": ["status"],
    "criado": ["criado_em"],
    "conclusao": ["data_conclusao"],
    "solicitante": ["comunicado__solicitante__first_name"],
}


def _tarefas_que_posso_responder(user):
    """IDs de Tarefas Pendentes onde o usuário é responsável direto, ou onde não
    há responsável definido e o usuário pertence ao departamento — mesma regra
    usada em minhas_tarefas para decidir quando mostrar o lápis de responder."""
    return set(
        Tarefa.objects.filter(status=StatusTarefa.PENDENTE)
        .filter(
            Q(responsavel=user)
            | Q(responsavel__isnull=True, departamento__responsaveis=user)
        )
        .values_list("pk", flat=True)
    )


def _contexto_lista_tarefas(request, tarefas):
    """Filtros/ordenação/paginação compartilhados entre Tarefas Abertas e Minhas
    Tarefas — mesma UI (ver tarefas/_lista_tarefas_corpo.html), só muda o
    queryset base."""
    tarefas = tarefas.select_related(
        "comunicado", "comunicado__solicitante", "departamento", "responsavel"
    )

    filtros = {
        "cai": request.GET.get("cai", "").strip(),
        "departamento": request.GET.get("departamento", "").strip(),
        "cliente": request.GET.get("cliente", "").strip(),
        "projeto": request.GET.get("projeto", "").strip(),
        "responsavel": request.GET.get("responsavel", "").strip(),
        "status": request.GET.get("status", "").strip(),
        "solicitante": request.GET.get("solicitante", "").strip(),
    }
    if filtros["cai"]:
        tarefas = tarefas.filter(comunicado__cai_fiscal__icontains=filtros["cai"])
    if filtros["departamento"]:
        tarefas = tarefas.filter(departamento_id=filtros["departamento"])
    if filtros["cliente"]:
        tarefas = tarefas.filter(comunicado__cliente=filtros["cliente"])
    if filtros["projeto"]:
        tarefas = tarefas.filter(comunicado__numero_projeto__icontains=filtros["projeto"])
    if filtros["responsavel"]:
        tarefas = tarefas.filter(responsavel_id=filtros["responsavel"])
    if filtros["status"]:
        tarefas = tarefas.filter(status=filtros["status"])
    if filtros["solicitante"]:
        tarefas = tarefas.filter(comunicado__solicitante_id=filtros["solicitante"])

    sort = request.GET.get("sort", "-cai")
    sort_campo = sort.lstrip("-")
    campos_model = SORT_CAMPOS.get(
        sort_campo, ["comunicado__ano_fiscal", "comunicado__numero_sequencial"]
    )
    if sort.startswith("-"):
        tarefas = tarefas.order_by(*[f"-{c}" for c in campos_model], "-id")
    else:
        tarefas = tarefas.order_by(*campos_model, "id")

    paginator = Paginator(tarefas, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    params_sem_page = {k: v for k, v in filtros.items() if v}
    if sort:
        params_sem_page["sort"] = sort
    qs_sem_page = urlencode(params_sem_page)

    params_sem_sort = {k: v for k, v in filtros.items() if v}
    qs_sem_sort = urlencode(params_sem_sort)

    sort_links = {}
    for chave in SORT_CAMPOS:
        proximo = f"-{chave}" if sort == chave else chave
        seta = "▲" if sort == chave else ("▼" if sort == f"-{chave}" else "")
        prefixo = f"{qs_sem_sort}&" if qs_sem_sort else ""
        sort_links[chave] = {"url": f"?{prefixo}sort={proximo}", "seta": seta}

    return {
        "page_obj": page_obj,
        "status_choices": StatusTarefa.choices,
        "departamentos": Departamento.objects.order_by("nome"),
        "clientes": Tarefa.objects.order_by("comunicado__cliente").values_list(
            "comunicado__cliente", flat=True
        ).distinct(),
        "responsaveis": User.objects.filter(tarefas_responsavel__isnull=False)
        .distinct()
        .order_by("first_name", "username"),
        "solicitantes": User.objects.filter(comunicados_solicitados__isnull=False)
        .distinct()
        .order_by("first_name", "username"),
        "filtros": filtros,
        "sort_links": sort_links,
        "qs_paginacao": f"{qs_sem_page}&" if qs_sem_page else "",
        "pode_responder_ids": _tarefas_que_posso_responder(request.user),
    }


@login_required
def listar_abertas(request):
    contexto = _contexto_lista_tarefas(request, Tarefa.objects.all())
    contexto["titulo"] = "Tarefas"
    contexto["url_limpar_filtros"] = reverse("tarefas:listar_abertas")
    return render(request, "tarefas/listar_abertas.html", contexto)


@login_required
def minhas_tarefas(request):
    tarefas = Tarefa.objects.filter(
        Q(responsavel=request.user)
        | Q(responsavel__isnull=True, departamento__responsaveis=request.user)
    ).distinct()
    contexto = _contexto_lista_tarefas(request, tarefas)
    contexto["titulo"] = "Minhas Tarefas"
    contexto["url_limpar_filtros"] = reverse("tarefas:minhas")
    return render(request, "tarefas/minhas.html", contexto)


@login_required
def cancelar_tarefa_view(request, pk):
    tarefa = get_object_or_404(Tarefa, pk=pk)
    if request.method == "POST":
        if tarefa.status == StatusTarefa.PENDENTE:
            cancelar_tarefa(tarefa)
            messages.success(request, "Tarefa cancelada.")
        else:
            messages.error(request, "Essa Tarefa não pode mais ser cancelada.")

    next_url = request.POST.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect("tarefas:listar_abertas")


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
