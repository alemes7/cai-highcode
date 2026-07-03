from django.conf import settings
from django.db import models

from comunicados.models import Comunicado
from core.models import Departamento, TimeStampedModel
from tarefas.models import Tarefa


class StatusAcao(models.TextChoices):
    PENDENTE = "PENDENTE", "Pendente"
    CONCLUIDO = "CONCLUIDO", "Concluído"
    CANCELADO = "CANCELADO", "Cancelado"


class Acao(TimeStampedModel):
    # FK direta ao Comunicado (além da Tarefa) para permitir queries diretas de listagem.
    comunicado = models.ForeignKey(
        Comunicado,
        on_delete=models.CASCADE,
        related_name="acoes",
    )
    tarefa = models.ForeignKey(
        Tarefa,
        on_delete=models.CASCADE,
        related_name="acoes",
    )
    descricao = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=StatusAcao.choices,
        default=StatusAcao.PENDENTE,
        db_index=True,
    )
    prazo_original = models.DateField(db_index=True)
    prazo_reajustado = models.DateField(
        null=True,
        blank=True,
        help_text="Quando preenchido, prevalece sobre o prazo original no cálculo de atraso.",
    )
    departamento = models.ForeignKey(
        Departamento,
        on_delete=models.PROTECT,
        related_name="acoes",
        help_text="Herdado da Tarefa de origem; preenchido automaticamente ao salvar.",
    )
    responsavel_nome = models.CharField(max_length=150, blank=True)
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="acoes_responsavel",
    )
    data_inclusao = models.DateField(auto_now_add=True)
    observacoes = models.TextField(blank=True)

    class Meta:
        ordering = ["prazo_original"]
        verbose_name = "Ação"
        verbose_name_plural = "Ações"

    @property
    def prazo_efetivo(self):
        return self.prazo_reajustado or self.prazo_original

    def save(self, *args, **kwargs):
        if not self.departamento_id:
            self.departamento_id = self.tarefa.departamento_id
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Ação #{self.pk} - {self.comunicado.cai_fiscal}"


class AcaoAnexo(models.Model):
    acao = models.ForeignKey(Acao, on_delete=models.CASCADE, related_name="anexos")
    arquivo = models.FileField(upload_to="acoes/anexos/%Y/%m/")
    nome_original = models.CharField(max_length=255, blank=True)
    enviado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Anexo"
        verbose_name_plural = "Anexos"

    def __str__(self):
        return self.nome_original or self.arquivo.name
