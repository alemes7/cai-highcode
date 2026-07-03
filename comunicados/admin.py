from django.contrib import admin

from tarefas.models import Tarefa

from .models import Comunicado, ComunicadoAnexo, ContadorCaiFiscal


class TarefaInline(admin.TabularInline):
    model = Tarefa
    extra = 0
    fields = ("departamento", "responsavel", "responsavel_nome", "status", "prazo")
    show_change_link = True


class ComunicadoAnexoInline(admin.TabularInline):
    model = ComunicadoAnexo
    extra = 0
    fields = ("arquivo", "nome_original", "enviado_em")
    readonly_fields = ("enviado_em",)


@admin.register(Comunicado)
class ComunicadoAdmin(admin.ModelAdmin):
    list_display = (
        "cai_fiscal",
        "cliente",
        "tipo",
        "status",
        "ano_fiscal",
        "data_criacao",
        "departamento_solicitante",
    )
    list_filter = ("status", "tipo", "ano_fiscal", "departamento_solicitante")
    search_fields = ("cai_fiscal", "cliente", "numero_projeto")
    date_hierarchy = "data_criacao"
    inlines = [TarefaInline, ComunicadoAnexoInline]
    autocomplete_fields = ["departamento_solicitante", "solicitante", "cancela_comunicado"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "departamento_solicitante", "solicitante", "cancela_comunicado"
        )


@admin.register(ContadorCaiFiscal)
class ContadorCaiFiscalAdmin(admin.ModelAdmin):
    list_display = ("ano_fiscal", "ultimo_numero")
