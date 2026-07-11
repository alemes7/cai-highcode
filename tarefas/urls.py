from django.urls import path

from . import views

app_name = "tarefas"

urlpatterns = [
    path("abertas/", views.listar_abertas, name="listar_abertas"),
    path("minhas/", views.minhas_tarefas, name="minhas"),
    path("<int:pk>/responder/", views.responder_tarefa_view, name="responder"),
    path("<int:pk>/cancelar/", views.cancelar_tarefa_view, name="cancelar"),
    path("responder/acoes/nova-linha/", views.nova_linha_acao, name="nova_linha_acao"),
]
