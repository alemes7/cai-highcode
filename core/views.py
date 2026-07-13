from datetime import date

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, DateField, DurationField, ExpressionWrapper, F, Q
from django.db.models.deletion import ProtectedError
from django.db.models.functions import Cast
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
    from acoes.models import Acao
    from comunicados.models import Comunicado
    from tarefas.models import Tarefa

    return render(
        request,
        "core/inicio.html",
        {
            "total_comunicados": f"{Comunicado.objects.count():,}".replace(",", "."),
            "total_tarefas": f"{Tarefa.objects.count():,}".replace(",", "."),
            "total_acoes": f"{Acao.objects.count():,}".replace(",", "."),
        },
    )


@login_required
def media_privado(request, path):
    """Serve os anexos (Comunicado/Tarefa/Ação) só para quem está logado —
    antes disso, qualquer um com a URL do /media/ baixava o arquivo sem
    autenticação nenhuma. Não restringe por dono/departamento, só por login,
    coerente com o resto do app (qualquer usuário autenticado já enxerga
    todos os Comunicados nas listas)."""
    return django_serve(request, path, document_root=settings.MEDIA_ROOT)


@login_required
def indicadores(request):
    """Todos os 4 gráficos são resolvidos com agregação no banco (Count/Avg com
    GROUP BY) em vez de trazer os registros pra Python e somar um por um — com
    dezenas de milhares de Tarefas/Ações, materializar cada linha como objeto
    Django antes de simplesmente contar é o que deixava essa tela lenta."""
    from acoes.models import Acao, StatusAcao
    from comunicados.models import Comunicado, StatusComunicado, TipoComunicado
    from tarefas.models import StatusTarefa, Tarefa

    # --- Gráfico 1: normas por ano fiscal — 1 query agrupando por ano_fiscal.
    # ano_fiscal já é "25'26" etc (2 dígitos com zero à esquerda), então a
    # ordenação alfabética do banco já é cronológica, sem precisar de _ordenar_ano_fiscal.
    por_ano = list(
        Comunicado.objects.values("ano_fiscal")
        .annotate(
            alteracao=Count("id", filter=Q(tipo=TipoComunicado.ALTERACAO)),
            introducao=Count("id", filter=Q(tipo=TipoComunicado.INTRODUCAO)),
            total=Count("id"),
            em_analise=Count("id", filter=Q(status=StatusComunicado.PENDENTE)),
        )
        .order_by("ano_fiscal")
    )
    grafico_normas = {
        "labels": [row["ano_fiscal"] for row in por_ano],
        "alteracao": [row["alteracao"] for row in por_ano],
        "introducao": [row["introducao"] for row in por_ano],
        "total": [row["total"] for row in por_ano],
        "em_analise": [row["em_analise"] for row in por_ano],
    }

    # --- Gráfico 2: Ações pendentes por área (atrasado vs no prazo) — 1 query.
    hoje = date.today()
    atrasada = Q(prazo_reajustado__isnull=False, prazo_reajustado__lt=hoje) | Q(
        prazo_reajustado__isnull=True, prazo_original__lt=hoje
    )
    por_dept_acoes = list(
        Acao.objects.filter(status=StatusAcao.PENDENTE)
        .values("departamento__nome")
        .annotate(atrasado=Count("id", filter=atrasada), total=Count("id"))
        .order_by("-total")
    )
    grafico_acoes = {
        "labels": [row["departamento__nome"] for row in por_dept_acoes],
        "atrasado": [row["atrasado"] for row in por_dept_acoes],
        "no_prazo": [row["total"] - row["atrasado"] for row in por_dept_acoes],
    }

    # --- Gráfico 3: Tarefas por departamento (analisado vs em análise) — 1 query.
    por_dept_tarefas = list(
        Tarefa.objects.values("departamento__nome")
        .annotate(
            em_analise=Count("id", filter=Q(status=StatusTarefa.PENDENTE)),
            total=Count("id"),
        )
        .order_by("-total")
    )
    grafico_tarefas = {
        "labels": [row["departamento__nome"] for row in por_dept_tarefas],
        "analisado": [row["total"] - row["em_analise"] for row in por_dept_tarefas],
        "em_analise": [row["em_analise"] for row in por_dept_tarefas],
    }

    # --- Gráfico 4: tempo médio de análise (dias) por departamento — 1 query,
    # com o AVG(data_conclusao - criado_em) calculado pelo Postgres.
    por_dept_tempo = list(
        Tarefa.objects.filter(data_conclusao__isnull=False)
        .annotate(
            dias=ExpressionWrapper(
                F("data_conclusao") - Cast("criado_em", output_field=DateField()),
                output_field=DurationField(),
            )
        )
        .values("departamento__nome")
        .annotate(tempo_medio=Avg("dias"))
        .order_by("-tempo_medio")
    )
    grafico_tempo = {
        "labels": [row["departamento__nome"] for row in por_dept_tempo],
        "tempo_medio": [
            round(row["tempo_medio"].total_seconds() / 86400, 1) for row in por_dept_tempo
        ],
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
def buscar_comunicados(request):
    """Endpoint HTMX do seletor "Número do CAI" do Painel Administrativo —
    busca ao vivo em vez de carregar todos os Comunicados num <select> só
    (com dezenas de milhares de registros isso vira uma página de vários
    MB e trava o carregamento)."""
    from comunicados.models import Comunicado

    termo = request.GET.get("q", "").strip()
    comunicados = []
    if termo:
        comunicados = Comunicado.objects.filter(
            Q(cai_fiscal__icontains=termo)
            | Q(cliente__icontains=termo)
            | Q(numero_projeto__icontains=termo)
        ).order_by("-ano_fiscal", "-numero_sequencial")[:20]
    return render(
        request,
        "core/_comunicados_resultado.html",
        {"comunicados": comunicados, "termo": termo},
    )


@login_required
@admin_required
def painel_administrativo(request):
    from comunicados.models import Comunicado

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
