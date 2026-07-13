from django import forms
from django.contrib.auth import get_user_model
from django.forms import formset_factory

from comunicados.forms import MultiFileField, MultiFileInput

from .models import StatusTarefa

User = get_user_model()

INPUT_CLASSES = (
    "w-full border border-slate-300 rounded px-3 py-2 bg-slate-50 "
    "focus:bg-white focus:outline-none focus:ring-1 focus:ring-sky-400"
)


class ResponderTarefaForm(forms.Form):
    # "" / "Pendente" fica como placeholder inicial: ChoiceField exige um valor
    # real dos outros 4 pra passar na validação (required=True por padrão),
    # então não dá pra "enviar" a resposta deixando em Pendente.
    DECISAO_CHOICES = [
        ("", "Pendente"),
        (
            StatusTarefa.APROVADO,
            "Sim, sem a necessidade de uma análise adicional.",
        ),
        (
            StatusTarefa.APROVADO_COM_ACOES,
            "Sim, mas necessita de ações adicionais sejam elas revisões de "
            "documentos, aquisições de equipamento, envolvimentos de "
            "fornecedores, RFQ.",
        ),
        (StatusTarefa.REJEITADO, "Não."),
        (StatusTarefa.NAO_SE_APLICA, "Não se aplica."),
    ]
    decisao = forms.ChoiceField(
        choices=DECISAO_CHOICES,
        label="A norma ou documento pode ser atendida?",
        widget=forms.Select(
            attrs={
                "class": INPUT_CLASSES,
                "onchange": (
                    "document.getElementById('acoes-wrapper').classList.toggle("
                    "'hidden', this.value !== 'APROVADO_COM_ACOES')"
                ),
            }
        ),
    )
    justificativa = forms.CharField(
        required=False,
        label="Justifique sua análise",
        widget=forms.Textarea(attrs={"class": INPUT_CLASSES, "rows": 2}),
    )
    envolver_outro_departamento = forms.ChoiceField(
        choices=[("NAO", "Não"), ("SIM", "Sim")],
        initial="NAO",
        widget=forms.Select(
            attrs={
                "class": INPUT_CLASSES,
                "onchange": (
                    "document.getElementById('escalonamento-wrapper').classList.toggle("
                    "'hidden', this.value !== 'SIM')"
                ),
            }
        ),
    )
    anexos = MultiFileField(
        required=False,
        label="Anexos",
        widget=MultiFileInput(attrs={"class": "hidden", "onchange": "atualizarAnexos(this)"}),
    )


class AcaoFormularioForm(forms.Form):
    descricao = forms.CharField(
        required=False,
        label="Ação Requerida",
        widget=forms.TextInput(attrs={"class": INPUT_CLASSES}),
    )
    prazo_original = forms.DateField(
        required=False,
        label="Prazo",
        widget=forms.DateInput(attrs={"class": INPUT_CLASSES, "type": "date"}),
    )
    responsavel = forms.ModelChoiceField(
        queryset=User.objects.all(),
        required=False,
        label="Responsável Principal",
        widget=forms.Select(attrs={"class": INPUT_CLASSES}),
    )

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("descricao"):
            if not cleaned_data.get("prazo_original"):
                raise forms.ValidationError("Informe o prazo para a ação.")
            if not cleaned_data.get("responsavel"):
                raise forms.ValidationError("Informe o responsável principal para a ação.")
        return cleaned_data


AcaoFormSet = formset_factory(AcaoFormularioForm, extra=1)
