from django.urls import path

from . import views

app_name = "acoes"

urlpatterns = [
    path("abertas/", views.listar_abertas, name="listar_abertas"),
    path("minhas/", views.minhas_acoes, name="minhas"),
    path("<int:pk>/concluir/", views.concluir_acao_view, name="concluir"),
    path("<int:pk>/cancelar/", views.cancelar_acao_view, name="cancelar"),
]
