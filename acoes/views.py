from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from core.models import Departamento

from .forms import ConcluirAcaoForm
from .models import Acao, AcaoAnexo, StatusAcao
from .services import cancelar_acao

User = get_user_model()

# Chave do filtro/ordenação (GET) -> campo(s) no model, para as telas de Ações.
# "cai" é composto: numero_sequencial sozinho reinicia a cada ano fiscal, então
# "137 / 23'24" apareceria antes de "5 / 25'26" se ordenássemos só por ele.
SORT_CAMPOS = {
    "cai": ["comunicado__ano_fiscal", "comunicado__numero_sequencial"],
    "status": ["status"],
    "cliente": ["comunicado__cliente"],
    "prazo": ["prazo_original"],
    "prazo_reajustado": ["prazo_reajustado"],
    "departamento": ["departamento__nome"],
    "conclusao": ["data_conclusao"],
    "responsavel": ["responsavel__first_name"],
    "solicitante": ["comunicado__solicitante__first_name"],
}


def _contexto_lista_acoes(request, acoes):
    """Filtros/ordenação/paginação compartilhados entre Ações Abertas e Minhas
    Ações — mesma UI (ver acoes/_lista_acoes_corpo.html), só muda o queryset base."""
    acoes = acoes.select_related(
        "comunicado", "comunicado__solicitante", "departamento", "responsavel", "tarefa"
    )

    filtros = {
        "cai": request.GET.get("cai", "").strip(),
        "departamento": request.GET.get("departamento", "").strip(),
        "cliente": request.GET.get("cliente", "").strip(),
        "responsavel": request.GET.get("responsavel", "").strip(),
        "status": request.GET.get("status", "").strip(),
        "solicitante": request.GET.get("solicitante", "").strip(),
    }
    if filtros["cai"]:
        acoes = acoes.filter(comunicado__cai_fiscal__icontains=filtros["cai"])
    if filtros["departamento"]:
        acoes = acoes.filter(departamento_id=filtros["departamento"])
    if filtros["cliente"]:
        acoes = acoes.filter(comunicado__cliente=filtros["cliente"])
    if filtros["responsavel"]:
        acoes = acoes.filter(responsavel_id=filtros["responsavel"])
    if filtros["status"]:
        acoes = acoes.filter(status=filtros["status"])
    if filtros["solicitante"]:
        acoes = acoes.filter(comunicado__solicitante_id=filtros["solicitante"])

    sort = request.GET.get("sort", "-cai")
    sort_campo = sort.lstrip("-")
    campos_model = SORT_CAMPOS.get(
        sort_campo, ["comunicado__ano_fiscal", "comunicado__numero_sequencial"]
    )
    if sort.startswith("-"):
        acoes = acoes.order_by(*[f"-{c}" for c in campos_model], "-id")
    else:
        acoes = acoes.order_by(*campos_model, "id")

    paginator = Paginator(acoes, 25)
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
        "status_choices": StatusAcao.choices,
        "departamentos": Departamento.objects.order_by("nome"),
        "clientes": Acao.objects.order_by("comunicado__cliente").values_list(
            "comunicado__cliente", flat=True
        ).distinct(),
        "responsaveis": User.objects.filter(acoes_responsavel__isnull=False)
        .distinct()
        .order_by("first_name", "username"),
        "solicitantes": User.objects.filter(comunicados_solicitados__isnull=False)
        .distinct()
        .order_by("first_name", "username"),
        "filtros": filtros,
        "sort_links": sort_links,
        "qs_paginacao": f"{qs_sem_page}&" if qs_sem_page else "",
        "pode_responder_ids": set(
            Acao.objects.filter(status=StatusAcao.PENDENTE, responsavel=request.user).values_list(
                "pk", flat=True
            )
        ),
    }


@login_required
def listar_abertas(request):
    contexto = _contexto_lista_acoes(request, Acao.objects.all())
    contexto["titulo"] = "Ações"
    contexto["url_limpar_filtros"] = reverse("acoes:listar_abertas")
    return render(request, "acoes/listar_abertas.html", contexto)


@login_required
def minhas_acoes(request):
    contexto = _contexto_lista_acoes(request, Acao.objects.filter(responsavel=request.user))
    contexto["titulo"] = "Minhas Ações"
    contexto["url_limpar_filtros"] = reverse("acoes:minhas")
    return render(request, "acoes/minhas.html", contexto)


@login_required
def cancelar_acao_view(request, pk):
    acao = get_object_or_404(Acao, pk=pk)
    if request.method == "POST":
        if acao.status == StatusAcao.PENDENTE:
            cancelar_acao(acao)
            messages.success(request, "Ação cancelada.")
        else:
            messages.error(request, "Essa Ação não pode mais ser cancelada.")

    next_url = request.POST.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect("acoes:listar_abertas")


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
            else:
                acao.data_conclusao = timezone.localdate()
            acao.status = novo_status
            acao.observacoes = form.cleaned_data["observacoes"]
            acao.save(
                update_fields=[
                    "status",
                    "prazo_reajustado",
                    "data_conclusao",
                    "observacoes",
                    "atualizado_em",
                ]
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
