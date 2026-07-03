from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    """Auditoria padrão: quem criou/editou e quando. Abstract para evitar clash de related_name."""

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        abstract = True


class Departamento(TimeStampedModel):
    nome = models.CharField(max_length=150, unique=True)
    empresa_unidade = models.CharField(max_length=150, blank=True)
    responsaveis = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="departamentos_responsavel",
        help_text="Usuários que recebem as tarefas quando a Tarefa não tem responsável definido.",
    )
    responsaveis_copia = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="departamentos_copia",
    )

    class Meta:
        ordering = ["nome"]
        verbose_name = "Departamento"
        verbose_name_plural = "Departamentos"

    def __str__(self):
        return self.nome
