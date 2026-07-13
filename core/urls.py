from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("indicadores/", views.indicadores, name="indicadores"),
    path("configuracoes/", views.configuracoes, name="configuracoes"),
    path(
        "configuracoes/departamentos/", views.departamentos_lista, name="departamentos_lista"
    ),
    path(
        "configuracoes/departamentos/novo/",
        views.departamento_form_fragment,
        name="departamento_form_novo",
    ),
    path(
        "configuracoes/departamentos/<int:pk>/editar/",
        views.departamento_form_fragment,
        name="departamento_form_editar",
    ),
    path(
        "configuracoes/departamentos/salvar/",
        views.departamento_salvar,
        name="departamento_criar",
    ),
    path(
        "configuracoes/departamentos/<int:pk>/salvar/",
        views.departamento_salvar,
        name="departamento_salvar",
    ),
    path(
        "configuracoes/departamentos/<int:pk>/excluir/",
        views.departamento_excluir,
        name="departamento_excluir",
    ),
    path(
        "configuracoes/departamentos/buscar-usuarios/",
        views.buscar_usuarios,
        name="buscar_usuarios",
    ),
    path("configuracoes/painel/", views.painel_administrativo, name="painel_administrativo"),
    path(
        "configuracoes/painel/buscar-comunicados/",
        views.buscar_comunicados,
        name="buscar_comunicados",
    ),
    path(
        "configuracoes/painel/alterar-responsavel/",
        views.alterar_responsavel_acao,
        name="alterar_responsavel_acao",
    ),
]
