from django.conf import settings
from django.db import models

from comunicados.models import Comunicado
from core.models import Departamento, TimeStampedModel


class StatusTarefa(models.TextChoices):
    PENDENTE = "PENDENTE", "Pendente"
    APROVADO = "APROVADO", "Aprovado"
    APROVADO_COM_ACOES = "APROVADO_COM_ACOES", "Aprovado com ações"
    REJEITADO = "REJEITADO", "Rejeitado"
    NAO_SE_APLICA = "NAO_SE_APLICA", "Não se aplica"
    CANCELADO = "CANCELADO", "Cancelado"


class Tarefa(TimeStampedModel):
    # FK para Comunicado é o filtro mais usado do sistema — já ganha índice por ser FK.
    comunicado = models.ForeignKey(
        Comunicado,
        on_delete=models.CASCADE,
        related_name="tarefas",
    )
    departamento = models.ForeignKey(
        Departamento,
        on_delete=models.PROTECT,
        related_name="tarefas",
    )
    # Escalonamento: ao responder uma Tarefa, o responsável pode envolver outro
    # departamento, criando uma nova Tarefa. Rastreamos a origem para auditoria/UI.
    tarefa_origem = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tarefas_geradas",
    )
    responsavel_nome = models.CharField(max_length=150, blank=True)
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tarefas_responsavel",
    )
    status = models.CharField(
        max_length=20,
        choices=StatusTarefa.choices,
        default=StatusTarefa.PENDENTE,
        db_index=True,
    )
    data_inicio = models.DateField(null=True, blank=True)
    data_conclusao = models.DateField(null=True, blank=True)
    # Padronizado como data (o SharePoint usava texto livre tipo "PrazoIATF"); permite
    # ordenação/filtro reais e alimenta o cálculo de atraso das Ações.
    prazo = models.DateField(null=True, blank=True)
    comentarios = models.TextField(blank=True)
    justificativa = models.TextField(blank=True)
    observacoes = models.TextField(blank=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "Tarefa"
        verbose_name_plural = "Tarefas"

    def __str__(self):
        return f"Tarefa #{self.pk} - {self.comunicado.cai_fiscal} - {self.departamento}"


class TarefaEmailCopia(models.Model):
    """Substitui a string separada por ';' do SharePoint por uma linha por e-mail em cópia."""

    tarefa = models.ForeignKey(Tarefa, on_delete=models.CASCADE, related_name="emails_copia")
    nome = models.CharField(max_length=150, blank=True)
    email = models.EmailField()

    class Meta:
        verbose_name = "E-mail em cópia"
        verbose_name_plural = "E-mails em cópia"
        constraints = [
            models.UniqueConstraint(fields=["tarefa", "email"], name="unique_email_copia_por_tarefa"),
        ]

    def __str__(self):
        return self.email


class TarefaAnexo(models.Model):
    tarefa = models.ForeignKey(Tarefa, on_delete=models.CASCADE, related_name="anexos")
    arquivo = models.FileField(upload_to="tarefas/anexos/%Y/%m/")
    nome_original = models.CharField(max_length=255, blank=True)
    enviado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Anexo"
        verbose_name_plural = "Anexos"

    def __str__(self):
        return self.nome_original or self.arquivo.name
