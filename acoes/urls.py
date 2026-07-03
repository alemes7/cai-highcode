from django.urls import path

from . import views

app_name = "acoes"

urlpatterns = [
    path("minhas-pendentes/", views.minhas_acoes_pendentes, name="minhas_pendentes"),
    path("<int:pk>/concluir/", views.concluir_acao_view, name="concluir"),
]
