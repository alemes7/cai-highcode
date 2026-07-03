from django.contrib import admin

from acoes.models import Acao

from .models import Tarefa, TarefaAnexo, TarefaEmailCopia


class TarefaEmailCopiaInline(admin.TabularInline):
    model = TarefaEmailCopia
    extra = 0


class TarefaAnexoInline(admin.TabularInline):
    model = TarefaAnexo
    extra = 0
    fields = ("arquivo", "nome_original", "enviado_em")
    readonly_fields = ("enviado_em",)


class AcaoInline(admin.TabularInline):
    model = Acao
    extra = 0
    fields = ("descricao", "status", "prazo_original", "prazo_reajustado", "responsavel")
    show_change_link = True


@admin.register(Tarefa)
class TarefaAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "comunicado",
        "departamento",
        "status",
        "responsavel",
        "responsavel_nome",
        "prazo",
        "data_conclusao",
    )
    list_filter = ("status", "departamento")
    search_fields = (
        "comunicado__cai_fiscal",
        "responsavel_nome",
        "responsavel__username",
    )
    autocomplete_fields = ["comunicado", "departamento", "responsavel", "tarefa_origem"]
    inlines = [TarefaEmailCopiaInline, TarefaAnexoInline, AcaoInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "comunicado", "departamento", "responsavel"
        )
