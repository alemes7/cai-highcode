from django import forms

INPUT_CLASSES = (
    "w-full border border-slate-300 rounded px-3 py-2 bg-slate-50 "
    "focus:bg-white focus:outline-none focus:ring-1 focus:ring-sky-400"
)


class DepartamentoForm(forms.Form):
    nome = forms.CharField(
        label="Departamento",
        max_length=150,
        widget=forms.TextInput(attrs={"class": INPUT_CLASSES}),
    )
    responsavel_obrigatorio = forms.BooleanField(
        required=False,
        label="Responsável obrigatório?",
        widget=forms.CheckboxInput(attrs={"class": "sr-only peer"}),
    )
