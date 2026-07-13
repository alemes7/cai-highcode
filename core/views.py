from collections import defaultdict
from datetime import date

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.static import serve as django_serve

from .decorators import admin_required
from .forms import DepartamentoForm
from .models import Departamento

User = get_user_model()

# Meta única (SLA) usada no gráfico "Tempo médio de análise" — fixa por enquanto;
# dá pra virar configurável por departamento quando a tela de Configurações existir.
META_DIAS_ANALISE = 10


@login_required
def inicio(request):
    return render(request, "core/inicio.html")


@login_required
def media_privado(request, path):
    """Serve os anexos (Comunicado/Tarefa/Ação) só para quem está logado —
    antes disso, qualquer um com a URL do /media/ baixava o arquivo sem
    autenticação nenhuma. Não restringe por dono/departamento, só por login,
    coerente com o resto do app (qualquer usuário autenticado já enxerga
    todos os Comunicados nas listas)."""
    return django_serve(request, path, document_root=settings.MEDIA_ROOT)


def _ordenar_ano_fiscal(ano_fiscal):
    # "25'26" -> 25, só para ordenar os rótulos cronologicamente no gráfico.
    return int(ano_fiscal.split("'")[0])


@login_required
def indicadores(request):
    from acoes.models import Acao, StatusAcao
    from comunicados.models import Comunicado, StatusComunicado, TipoComunicado
    from tarefas.models import StatusTarefa, Tarefa

    anos_fiscais = sorted(
        Comunicado.objects.order_by().values_list("ano_fiscal", flat=True).distinct(),
        key=_ordenar_ano_fiscal,
    )
    grafico_normas = {"labels": anos_fiscais, "alteracao": [], "introducao": [], "total": [], "em_analise": []}
    for ano in anos_fiscais:
        comunicados_ano = Comunicado.objects.filter(ano_fiscal=ano)
        grafico_normas["alteracao"].append(
            comunicados_ano.filter(tipo=TipoComunicado.ALTERACAO).count()
        )
        grafico_normas["introducao"].append(
            comunicados_ano.filter(tipo=TipoComunicado.INTRODUCAO).count()
        )
        grafico_normas["total"].append(comunicados_ano.count())
        grafico_normas["em_analise"].append(
            comunicados_ano.filter(status=StatusComunicado.PENDENTE).count()
        )

    hoje = date.today()
    contagem_acoes = defaultdict(lambda: {"atrasado": 0, "no_prazo": 0})
    for acao in Acao.objects.filter(status=StatusAcao.PENDENTE).select_related("departamento"):
        chave = "atrasado" if acao.prazo_efetivo < hoje else "no_prazo"
        contagem_acoes[acao.departamento.nome][chave] += 1
    departamentos_acoes = sorted(
        contagem_acoes,
        key=lambda d: contagem_acoes[d]["atrasado"] + contagem_acoes[d]["no_prazo"],
        reverse=True,
    )
    grafico_acoes = {
        "labels": departamentos_acoes,
        "atrasado": [contagem_acoes[d]["atrasado"] for d in departamentos_acoes],
        "no_prazo": [contagem_acoes[d]["no_prazo"] for d in departamentos_acoes],
    }

    contagem_tarefas = defaultdict(lambda: {"analisado": 0, "em_analise": 0})
    for tarefa in Tarefa.objects.select_related("departamento"):
        chave = "em_analise" if tarefa.status == StatusTarefa.PENDENTE else "analisado"
        contagem_tarefas[tarefa.departamento.nome][chave] += 1
    departamentos_tarefas = sorted(
        contagem_tarefas,
        key=lambda d: contagem_tarefas[d]["analisado"] + contagem_tarefas[d]["em_analise"],
        reverse=True,
    )
    grafico_tarefas = {
        "labels": departamentos_tarefas,
        "analisado": [contagem_tarefas[d]["analisado"] for d in departamentos_tarefas],
        "em_analise": [contagem_tarefas[d]["em_analise"] for d in departamentos_tarefas],
    }

    soma_dias = defaultdict(lambda: [0, 0])
    for tarefa in Tarefa.objects.filter(data_conclusao__isnull=False).select_related("departamento"):
        dias = (tarefa.data_conclusao - tarefa.criado_em.date()).days
        soma_dias[tarefa.departamento.nome][0] += dias
        soma_dias[tarefa.departamento.nome][1] += 1
    departamentos_tempo = sorted(
        soma_dias, key=lambda d: soma_dias[d][0] / soma_dias[d][1], reverse=True
    )
    grafico_tempo = {
        "labels": departamentos_tempo,
        "tempo_medio": [round(soma_dias[d][0] / soma_dias[d][1], 1) for d in departamentos_tempo],
        "meta": META_DIAS_ANALISE,
    }

    return render(
        request,
        "core/indicadores.html",
        {
            "grafico_normas": grafico_normas,
            "grafico_acoes": grafico_acoes,
            "grafico_tarefas": grafico_tarefas,
            "grafico_tempo": grafico_tempo,
        },
    )


@login_required
@admin_required
def configuracoes(request):
    return render(request, "core/configuracoes.html")


SORT_CAMPOS_DEPARTAMENTO = {"id": "pk", "departamento": "nome"}


@login_required
@admin_required
def departamentos_lista(request):
    departamentos = Departamento.objects.prefetch_related("responsaveis", "responsaveis_copia")

    filtros = {
        "id": request.GET.get("id", "").strip(),
        "departamento": request.GET.get("departamento", "").strip(),
        "responsavel": request.GET.get("responsavel", "").strip(),
        "responsavel_copia": request.GET.get("responsavel_copia", "").strip(),
    }
    if filtros["id"]:
        departamentos = departamentos.filter(pk=filtros["id"])
    if filtros["departamento"]:
        departamentos = departamentos.filter(nome=filtros["departamento"])
    if filtros["responsavel"]:
        termo = filtros["responsavel"]
        departamentos = departamentos.filter(
            Q(responsaveis__first_name__icontains=termo)
            | Q(responsaveis__last_name__icontains=termo)
            | Q(responsaveis__username__icontains=termo)
        ).distinct()
    if filtros["responsavel_copia"]:
        termo = filtros["responsavel_copia"]
        departamentos = departamentos.filter(
            Q(responsaveis_copia__first_name__icontains=termo)
            | Q(responsaveis_copia__last_name__icontains=termo)
            | Q(responsaveis_copia__username__icontains=termo)
        ).distinct()

    sort = request.GET.get("sort", "id")
    sort_campo = sort.lstrip("-")
    campo_model = SORT_CAMPOS_DEPARTAMENTO.get(sort_campo, "pk")
    if sort.startswith("-"):
        departamentos = departamentos.order_by(f"-{campo_model}")
    else:
        departamentos = departamentos.order_by(campo_model)

    sort_links = {}
    for chave in SORT_CAMPOS_DEPARTAMENTO:
        proximo = f"-{chave}" if sort == chave else chave
        seta = "▲" if sort == chave else ("▼" if sort == f"-{chave}" else "")
        sort_links[chave] = {"url": f"?sort={proximo}", "seta": seta}

    return render(
        request,
        "core/departamentos_lista.html",
        {
            "departamentos": departamentos,
            "todos_departamentos": Departamento.objects.order_by("nome"),
            "filtros": filtros,
            "sort_links": sort_links,
        },
    )


@login_required
@admin_required
def departamento_form_fragment(request, pk=None):
    """Devolve o corpo do modal de Criar/Editar Departamento via HTMX — usado
    tanto pelo botão "Adicionar +" (pk=None) quanto pelo lápis de cada linha."""
    departamento = get_object_or_404(Departamento, pk=pk) if pk else None
    form = DepartamentoForm(
        initial={
            "nome": departamento.nome if departamento else "",
            "responsavel_obrigatorio": departamento.responsavel_obrigatorio if departamento else False,
        }
    )
    form_action = (
        reverse("core:departamento_salvar", args=[departamento.pk])
        if departamento
        else reverse("core:departamento_criar")
    )
    return render(
        request,
        "core/_departamento_form_modal.html",
        {
            "form": form,
            "departamento": departamento,
            "responsaveis_atuais": departamento.responsaveis.all() if departamento else [],
            "responsaveis_copia_atuais": departamento.responsaveis_copia.all() if departamento else [],
            "form_action": form_action,
        },
    )


@login_required
@admin_required
def departamento_salvar(request, pk=None):
    if request.method != "POST":
        return redirect("core:departamentos_lista")

    departamento = get_object_or_404(Departamento, pk=pk) if pk else None
    form = DepartamentoForm(request.POST)
    responsaveis_ids = request.POST.getlist("responsaveis")
    responsaveis_copia_ids = request.POST.getlist("responsaveis_copia")

    if form.is_valid():
        nome = form.cleaned_data["nome"]
        duplicado = Departamento.objects.filter(nome__iexact=nome)
        if departamento:
            duplicado = duplicado.exclude(pk=departamento.pk)
        if duplicado.exists():
            form.add_error("nome", "Já existe um departamento com esse nome.")
        elif not responsaveis_ids:
            form.add_error(None, "Informe ao menos um Responsável Principal.")

    if form.is_valid() and responsaveis_ids:
        if departamento:
            departamento.nome = form.cleaned_data["nome"]
            departamento.responsavel_obrigatorio = form.cleaned_data["responsavel_obrigatorio"]
            departamento.save()
        else:
            departamento = Departamento.objects.create(
                nome=form.cleaned_data["nome"],
                responsavel_obrigatorio=form.cleaned_data["responsavel_obrigatorio"],
            )
        departamento.responsaveis.set(responsaveis_ids)
        departamento.responsaveis_copia.set(responsaveis_copia_ids)
        messages.success(request, f"Departamento {departamento.nome} salvo.")
    else:
        erro = form.errors.get("nome") or form.non_field_errors() or None
        messages.error(
            request,
            erro[0] if erro else "Não foi possível salvar o departamento — confira os dados.",
        )

    return redirect("core:departamentos_lista")


@login_required
@admin_required
def departamento_excluir(request, pk):
    departamento = get_object_or_404(Departamento, pk=pk)
    if request.method == "POST":
        nome = departamento.nome
        try:
            departamento.delete()
            messages.success(request, f"Departamento {nome} excluído.")
        except ProtectedError:
            messages.error(
                request,
                f"Não é possível excluir {nome}: há Comunicados, Tarefas ou Ações "
                "vinculados a esse departamento.",
            )
    return redirect("core:departamentos_lista")


@login_required
@admin_required
def buscar_usuarios(request):
    """Endpoint HTMX reaproveitado nos dois popups de busca de usuário (Editar
    Departamento e Painel Administrativo): busca ao vivo por nome/usuário
    (substitui a busca no Azure AD do Power Apps original)."""
    termo = request.GET.get("q", "").strip()
    usuarios = []
    if termo:
        usuarios = User.objects.filter(
            Q(first_name__icontains=termo)
            | Q(last_name__icontains=termo)
            | Q(username__icontains=termo)
        ).order_by("first_name", "username")[:20]
    return render(
        request, "core/_usuarios_resultado.html", {"usuarios": usuarios, "termo": termo}
    )


@login_required
@admin_required
def painel_administrativo(request):
    from acoes.models import Acao
    from comunicados.models import Comunicado

    comunicados = Comunicado.objects.order_by("-numero_sequencial")
    comunicado = None
    tarefas = []
    acoes = []

    comunicado_id = request.GET.get("comunicado")
    if comunicado_id:
        comunicado = get_object_or_404(
            Comunicado.objects.select_related("departamento_solicitante", "solicitante"),
            pk=comunicado_id,
        )
        tarefas = comunicado.tarefas.select_related("departamento", "responsavel").order_by(
            "criado_em"
        )
        acoes = comunicado.acoes.select_related("departamento", "responsavel").order_by(
            "prazo_original"
        )

    return render(
        request,
        "core/painel_administrativo.html",
        {
            "comunicados": comunicados,
            "comunicado": comunicado,
            "tarefas": tarefas,
            "acoes": acoes,
        },
    )


@login_required
@admin_required
def alterar_responsavel_acao(request):
    """Endpoint do popup "Alterar Responsável" do Painel Administrativo — troca
    o responsável de uma Ação específica (ex: pessoa saiu da empresa), sem
    passar pelo fluxo normal de concluir a Ação."""
    from acoes.models import Acao

    if request.method != "POST":
        return redirect("core:painel_administrativo")

    acao = get_object_or_404(Acao, pk=request.POST.get("acao_id"))
    responsavel_id = request.POST.get("responsavel_id")

    if responsavel_id:
        acao.responsavel = get_object_or_404(User, pk=responsavel_id)
        acao.save(update_fields=["responsavel", "atualizado_em"])
        messages.success(request, "Responsável da Ação atualizado.")
    else:
        messages.error(request, "Selecione um usuário antes de confirmar.")

    url = reverse("core:painel_administrativo")
    comunicado_id = request.POST.get("comunicado_id")
    if comunicado_id:
        url = f"{url}?comunicado={comunicado_id}"
    return redirect(url)
