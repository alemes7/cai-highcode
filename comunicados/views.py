from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from core.models import Departamento

from .forms import ComunicadoForm, TarefaInicialForm, TarefaInicialFormSet
from .models import Comunicado, StatusComunicado, TipoComunicado
from .services import cancelar_comunicado, criar_comunicado

User = get_user_model()

# Chave do filtro/ordenação (GET) -> nome do campo no model, para a tela de Comunicados abertos.
SORT_CAMPOS = {
    "cai": "numero_sequencial",
    "data": "data_criacao",
    "cliente": "cliente",
    "projeto": "numero_projeto",
    "tipo": "tipo",
    "solicitante": "solicitante__first_name",
    "status": "status",
}


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


def _contexto_lista_comunicados(request, comunicados):
    """Monta filtros/ordenação/paginação compartilhados entre Comunicados Abertos
    e Meus Comunicados — as duas telas usam exatamente a mesma UI (ver
    comunicados/_lista_comunicados_corpo.html), só muda o queryset base."""
    comunicados = comunicados.select_related("departamento_solicitante", "solicitante")

    filtros = {
        "cai": request.GET.get("cai", "").strip(),
        "data": request.GET.get("data", "").strip(),
        "cliente": request.GET.get("cliente", "").strip(),
        "projeto": request.GET.get("projeto", "").strip(),
        "tipo": request.GET.get("tipo", "").strip(),
        "solicitante": request.GET.get("solicitante", "").strip(),
        "status": request.GET.get("status", "").strip(),
    }
    if filtros["cai"]:
        comunicados = comunicados.filter(cai_fiscal__icontains=filtros["cai"])
    if filtros["data"]:
        comunicados = comunicados.filter(data_criacao=filtros["data"])
    if filtros["cliente"]:
        comunicados = comunicados.filter(cliente=filtros["cliente"])
    if filtros["projeto"]:
        comunicados = comunicados.filter(numero_projeto__icontains=filtros["projeto"])
    if filtros["tipo"]:
        comunicados = comunicados.filter(tipo=filtros["tipo"])
    if filtros["solicitante"]:
        comunicados = comunicados.filter(solicitante_id=filtros["solicitante"])
    if filtros["status"]:
        comunicados = comunicados.filter(status=filtros["status"])

    sort = request.GET.get("sort", "-cai")
    sort_campo = sort.lstrip("-")
    campo_model = SORT_CAMPOS.get(sort_campo, "numero_sequencial")
    if sort.startswith("-"):
        comunicados = comunicados.order_by(f"-{campo_model}", "-id")
    else:
        comunicados = comunicados.order_by(campo_model, "id")

    paginator = Paginator(comunicados, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    # Querystring sem 'page' (pra paginação) e sem 'sort' (pra cabeçalhos ordenáveis),
    # sempre preservando os filtros ativos.
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
        "status_choices": StatusComunicado.choices,
        "tipo_choices": TipoComunicado.choices,
        "clientes": Comunicado.objects.order_by("cliente").values_list(
            "cliente", flat=True
        ).distinct(),
        "solicitantes": User.objects.filter(
            comunicados_solicitados__isnull=False
        ).distinct().order_by("first_name", "username"),
        "filtros": filtros,
        "sort_links": sort_links,
        "qs_paginacao": f"{qs_sem_page}&" if qs_sem_page else "",
    }


@login_required
def listar_abertos(request):
    contexto = _contexto_lista_comunicados(request, Comunicado.objects.all())
    contexto["titulo"] = "Comunicados"
    contexto["url_limpar_filtros"] = reverse("comunicados:listar_abertos")
    return render(request, "comunicados/lista_abertos.html", contexto)


@login_required
def meus_comunicados(request):
    contexto = _contexto_lista_comunicados(
        request, Comunicado.objects.filter(criado_por=request.user)
    )
    contexto["titulo"] = "Meus Comunicados"
    contexto["url_limpar_filtros"] = reverse("comunicados:meus")
    return render(request, "comunicados/meus.html", contexto)


@login_required
def cancelar_comunicado_view(request, pk):
    comunicado = get_object_or_404(Comunicado, pk=pk)
    if request.method == "POST":
        if comunicado.status == StatusComunicado.PENDENTE:
            cancelar_comunicado(comunicado)
            messages.success(request, f"Comunicado {comunicado.cai_fiscal} cancelado.")
        else:
            messages.error(request, "Esse Comunicado não pode mais ser cancelado.")

    next_url = request.POST.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect("comunicados:listar_abertos")
