from django.contrib import admin

from .models import Departamento


@admin.register(Departamento)
class DepartamentoAdmin(admin.ModelAdmin):
    list_display = ("nome", "empresa_unidade", "criado_em")
    search_fields = ("nome", "empresa_unidade")
    filter_horizontal = ("responsaveis", "responsaveis_copia")
