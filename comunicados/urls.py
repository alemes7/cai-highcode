from django.urls import path

from . import views

app_name = "comunicados"

urlpatterns = [
    path("novo/", views.novo_comunicado, name="novo"),
    path("novo/tarefas/nova-linha/", views.nova_linha_tarefa, name="nova_linha_tarefa"),
    path("novo/tarefas/info-departamento/", views.info_departamento, name="info_departamento"),
    path("meus/", views.meus_comunicados, name="meus"),
    path("abertos/", views.listar_abertos, name="listar_abertos"),
    path("<int:pk>/", views.detalhe_comunicado, name="detalhe"),
    path("<int:pk>/cancelar/", views.cancelar_comunicado_view, name="cancelar"),
]
