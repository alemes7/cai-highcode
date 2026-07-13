from django import forms

from comunicados.forms import MultiFileField, MultiFileInput

from .models import StatusAcao

INPUT_CLASSES = (
    "w-full border border-slate-300 rounded px-3 py-2 bg-slate-50 "
    "focus:bg-white focus:outline-none focus:ring-1 focus:ring-sky-400"
)


class ConcluirAcaoForm(forms.Form):
    STATUS_CHOICES = [
        (StatusAcao.PENDENTE, "Pendente"),
        (StatusAcao.CONCLUIDO, "Concluído"),
        (StatusAcao.CANCELADO, "Cancelado"),
    ]
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        widget=forms.Select(
            attrs={
                "class": INPUT_CLASSES,
                "onchange": (
                    "document.getElementById('id_prazo_reajustado')"
                    ".disabled = this.value !== 'PENDENTE'"
                ),
            }
        ),
    )
    prazo_reajustado = forms.DateField(
        required=False,
        label="Prazo reajustado",
        widget=forms.DateInput(attrs={"class": INPUT_CLASSES, "type": "date"}),
    )
    observacoes = forms.CharField(
        required=False,
        label="Observações Adicionais",
        widget=forms.Textarea(attrs={"class": INPUT_CLASSES, "rows": 2}),
    )
    anexos = MultiFileField(
        required=False,
        label="Anexos",
        widget=MultiFileInput(attrs={"class": "hidden", "onchange": "atualizarAnexos(this)"}),
    )
