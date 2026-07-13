from pathlib import Path

from django import forms
from django.contrib.auth import get_user_model
from django.forms import formset_factory
from django.urls import reverse_lazy

from core.models import Departamento

from .models import Comunicado, TipoComunicado

User = get_user_model()

INPUT_CLASSES = (
    "w-full border border-slate-300 rounded px-3 py-2 bg-slate-50 "
    "focus:bg-white focus:outline-none focus:ring-1 focus:ring-sky-400"
)
DISABLED_CLASSES = "w-full border border-slate-300 rounded px-3 py-2 bg-slate-100 text-slate-600"

# Extensões de documento de negócio esperadas para anexos de Comunicado/Tarefa/
# Ação — bloqueia tipos executáveis/script (ex: .exe, .html, .svg com script
# embutido) que poderiam ser abertos direto pelo navegador a partir do /media/.
EXTENSOES_ANEXO_PERMITIDAS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".png", ".jpg", ".jpeg", ".gif", ".txt", ".csv", ".zip", ".msg", ".eml",
}
TAMANHO_MAXIMO_ANEXO_MB = 15


class MultiFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

    def value_from_datadict(self, data, files, name):
        upload = files.getlist(name)
        return upload or None


class MultiFileField(forms.FileField):
    """Padrão documentado do Django para permitir múltiplos arquivos em um único
    campo (a validação do FileField normal só aceita um arquivo por vez)."""

    widget = MultiFileInput

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if not data:
            if self.required:
                raise forms.ValidationError(self.error_messages["required"], code="required")
            return []

        arquivos = []
        for arquivo in data:
            single_file_clean(arquivo, initial)

            extensao = Path(arquivo.name).suffix.lower()
            if extensao not in EXTENSOES_ANEXO_PERMITIDAS:
                raise forms.ValidationError(
                    f'Tipo de arquivo não permitido: "{arquivo.name}". '
                    f"Extensões aceitas: {', '.join(sorted(EXTENSOES_ANEXO_PERMITIDAS))}."
                )
            if arquivo.size > TAMANHO_MAXIMO_ANEXO_MB * 1024 * 1024:
                raise forms.ValidationError(
                    f'O arquivo "{arquivo.name}" excede o limite de '
                    f"{TAMANHO_MAXIMO_ANEXO_MB}MB."
                )
            arquivos.append(arquivo)
        return arquivos


class ComunicadoForm(forms.Form):
    tipo = forms.ChoiceField(
        choices=TipoComunicado.choices,
        label="Introdução ou Alteração?",
        widget=forms.Select(attrs={"class": INPUT_CLASSES}),
    )
    departamento_solicitante = forms.ModelChoiceField(
        queryset=Departamento.objects.all(),
        label="Departamento",
        widget=forms.Select(attrs={"class": INPUT_CLASSES}),
    )
    solicitante = forms.ModelChoiceField(
        queryset=User.objects.all(),
        label="Solicitante da abertura do Comunicado",
        widget=forms.Select(attrs={"class": INPUT_CLASSES}),
    )
    cliente = forms.CharField(
        max_length=150, widget=forms.TextInput(attrs={"class": INPUT_CLASSES})
    )
    numero_projeto = forms.CharField(
        max_length=100, label="Número", widget=forms.TextInput(attrs={"class": INPUT_CLASSES})
    )
    data_cai = forms.DateField(
        required=False,
        label="Data",
        widget=forms.DateInput(attrs={"class": INPUT_CLASSES, "type": "date"}),
    )
    revisao = forms.CharField(
        max_length=50, required=False, widget=forms.TextInput(attrs={"class": INPUT_CLASSES})
    )
    comentarios = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"class": INPUT_CLASSES, "rows": 2})
    )

    possui_cai_cancelado = forms.BooleanField(
        required=False,
        label="Este Comunicado cancela/substitui algum outro?",
        widget=forms.CheckboxInput(
            attrs={
                "class": "sr-only peer",
                "onchange": (
                    "document.getElementById('cai-cancelado-wrapper')"
                    ".classList.toggle('hidden', !this.checked)"
                ),
            }
        ),
    )
    cai_cancelado_fiscal = forms.CharField(
        required=False,
        label="Nº do Comunicado",
        widget=forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "ex: 51 / 25'26"}),
    )

    anexos = MultiFileField(
        required=False,
        label="Anexos",
        widget=MultiFileInput(attrs={"class": "hidden", "onchange": "atualizarAnexos(this)"}),
    )

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("possui_cai_cancelado"):
            codigo = (cleaned_data.get("cai_cancelado_fiscal") or "").strip()
            if not codigo:
                self.add_error(
                    "cai_cancelado_fiscal", "Informe o número do Comunicado a cancelar."
                )
            else:
                try:
                    cleaned_data["cancela_comunicado"] = Comunicado.objects.get(
                        cai_fiscal=codigo
                    )
                except Comunicado.DoesNotExist:
                    self.add_error(
                        "cai_cancelado_fiscal", "Nenhum Comunicado encontrado com esse número."
                    )
        else:
            cleaned_data["cancela_comunicado"] = None
        return cleaned_data


class TarefaInicialForm(forms.Form):
    departamento = forms.ModelChoiceField(
        queryset=Departamento.objects.all(),
        required=False,
        widget=forms.Select(
            attrs={
                "class": INPUT_CLASSES,
                "hx-get": reverse_lazy("comunicados:info_departamento"),
                "hx-target": "next .tarefa-info-display",
                "hx-swap": "innerHTML",
                "hx-trigger": "change",
            }
        ),
    )
    responsavel_principal = forms.ModelChoiceField(
        queryset=User.objects.all(),
        required=False,
        label="Responsável Principal",
        widget=forms.Select(attrs={"class": INPUT_CLASSES}),
    )
    comentarios = forms.CharField(
        required=False,
        label="Comentários e Observações",
        widget=forms.Textarea(attrs={"class": INPUT_CLASSES, "rows": 2}),
    )

    def clean(self):
        cleaned_data = super().clean()
        departamento = cleaned_data.get("departamento")
        if departamento and departamento.responsavel_obrigatorio and not cleaned_data.get(
            "responsavel_principal"
        ):
            self.add_error(
                "responsavel_principal",
                f"O departamento {departamento} exige um responsável principal específico.",
            )
        return cleaned_data


TarefaInicialFormSet = formset_factory(TarefaInicialForm, extra=1)
