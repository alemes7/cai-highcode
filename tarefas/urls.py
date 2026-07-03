from django.urls import path

from . import views

app_name = "tarefas"

urlpatterns = [
    path("minhas-pendentes/", views.minhas_tarefas_pendentes, name="minhas_pendentes"),
    path("<int:pk>/responder/", views.responder_tarefa_view, name="responder"),
    path("responder/acoes/nova-linha/", views.nova_linha_acao, name="nova_linha_acao"),
]
