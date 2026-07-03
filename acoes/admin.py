from django.contrib import admin

from .models import Acao, AcaoAnexo


class AcaoAnexoInline(admin.TabularInline):
    model = AcaoAnexo
    extra = 0
    fields = ("arquivo", "nome_original", "enviado_em")
    readonly_fields = ("enviado_em",)


@admin.register(Acao)
class AcaoAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "comunicado",
        "tarefa",
        "status",
        "prazo_original",
        "prazo_reajustado",
        "departamento",
        "responsavel",
        "responsavel_nome",
    )
    list_filter = ("status", "departamento")
    search_fields = (
        "comunicado__cai_fiscal",
        "descricao",
        "responsavel_nome",
        "responsavel__username",
    )
    autocomplete_fields = ["comunicado", "tarefa", "departamento", "responsavel"]
    inlines = [AcaoAnexoInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "comunicado", "tarefa", "departamento", "responsavel"
        )
