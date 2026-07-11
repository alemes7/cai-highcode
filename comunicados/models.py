from django.conf import settings
from django.db import models

from core.models import Departamento, TimeStampedModel


class StatusComunicado(models.TextChoices):
    PENDENTE = "PENDENTE", "Pendente"
    APROVADO = "APROVADO", "Aprovado"
    APROVADO_COM_ACOES = "APROVADO_COM_ACOES", "Aprovado com ações"
    REJEITADO = "REJEITADO", "Rejeitado"
    CANCELADO = "CANCELADO", "Cancelado"


class TipoComunicado(models.TextChoices):
    INTRODUCAO = "INTRODUCAO", "Introdução"
    ALTERACAO = "ALTERACAO", "Alteração"


class Comunicado(TimeStampedModel):
    # Ano fiscal thyssenkrupp: outubro a setembro, rótulo tipo "25'26" (ver
    # comunicados.services.calcular_ano_fiscal). Não é um ano civil simples.
    ano_fiscal = models.CharField(max_length=10, db_index=True)
    # Sequencial que reseta a cada virada de ano fiscal (1º de outubro).
    # Gerado por comunicados.services.criar_comunicado, nunca editado à mão.
    numero_sequencial = models.PositiveIntegerField(editable=False)
    # Referência pública do CAI, ex: "51 / 25'26" = numero_sequencial + ano_fiscal.
    cai_fiscal = models.CharField(
        max_length=30,
        unique=True,
        blank=True,
        editable=False,
        help_text="Gerado automaticamente (ex: 51 / 25'26).",
    )
    data_criacao = models.DateField(db_index=True)
    # Data do CAI (form1datacai) — opcional, distinta de data_criacao (auto/hoje).
    data_cai = models.DateField(null=True, blank=True)
    tipo = models.CharField(max_length=15, choices=TipoComunicado.choices)
    revisao = models.CharField(max_length=50, blank=True)

    departamento_solicitante = models.ForeignKey(
        Departamento,
        on_delete=models.PROTECT,
        related_name="comunicados_solicitados",
    )
    # Quem PEDIU a abertura do CAI (form1solnamecai) — é escolhido de uma lista
    # de usuários, nem sempre é quem preenche o formulário (isso é criado_por,
    # herdado de TimeStampedModel e preenchido a partir do usuário logado).
    solicitante = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="comunicados_solicitados",
    )

    cliente = models.CharField(max_length=150, db_index=True)
    numero_projeto = models.CharField(max_length=100)

    cancela_comunicado = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cancelado_por",
        help_text="Outro Comunicado que este substitui, se houver.",
    )

    comentarios = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=StatusComunicado.choices,
        default=StatusComunicado.PENDENTE,
        db_index=True,
    )
    observacoes = models.TextField(blank=True)

    class Meta:
        ordering = ["-data_criacao", "-id"]
        verbose_name = "Comunicado"
        verbose_name_plural = "Comunicados"
        constraints = [
            models.UniqueConstraint(
                fields=["ano_fiscal", "numero_sequencial"],
                name="unique_numero_sequencial_por_ano_fiscal",
            ),
        ]

    def __str__(self):
        return self.cai_fiscal or f"Comunicado #{self.pk}"


class ComunicadoAnexo(models.Model):
    comunicado = models.ForeignKey(Comunicado, on_delete=models.CASCADE, related_name="anexos")
    arquivo = models.FileField(upload_to="comunicados/anexos/%Y/%m/")
    nome_original = models.CharField(max_length=255, blank=True)
    enviado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Anexo"
        verbose_name_plural = "Anexos"

    def __str__(self):
        return self.nome_original or self.arquivo.name


class ContadorCaiFiscal(models.Model):
    """Uma linha por ano fiscal, travada via select_for_update() em
    comunicados.services.criar_comunicado() para gerar numero_sequencial sem
    gaps/duplicatas mesmo com criação concorrente — inclusive na primeira
    Comunicado de um ano fiscal novo, quando ainda não há nenhuma linha em
    Comunicado para travar."""

    ano_fiscal = models.CharField(max_length=10, unique=True)
    ultimo_numero = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Contador de Numeração Fiscal"
        verbose_name_plural = "Contadores de Numeração Fiscal"

    def __str__(self):
        return f"{self.ano_fiscal} (último: {self.ultimo_numero})"
