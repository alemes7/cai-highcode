from datetime import timedelta

from celery import shared_task
from django.db.models.functions import Coalesce
from django.utils import timezone

from core.emails import enviar_email


@shared_task
def notificar_nova_acao(acao_id):
    from .models import Acao

    acao = Acao.objects.select_related("responsavel", "comunicado").get(pk=acao_id)

    if not acao.responsavel or not acao.responsavel.email:
        return

    enviar_email(
        assunto=f"[CAI] Nova ação - {acao.comunicado.cai_fiscal}",
        corpo=(
            f"Uma nova ação foi atribuída a você no Comunicado "
            f"{acao.comunicado.cai_fiscal}.\n\n"
            f"Descrição: {acao.descricao}\n"
            f"Prazo: {acao.prazo_original.isoformat()}\n"
        ),
        destinatarios=[acao.responsavel.email],
    )


@shared_task
def verificar_prazos_acoes():
    """Roda 2x/dia via Celery Beat. Usa prazo_reajustado quando preenchido,
    senão prazo_original, e avisa quem estiver a <=5 dias do prazo ou atrasado."""
    from .models import Acao, StatusAcao

    limite = timezone.localdate() + timedelta(days=5)
    acoes = (
        Acao.objects.filter(status=StatusAcao.PENDENTE)
        .annotate(prazo_efetivo_calc=Coalesce("prazo_reajustado", "prazo_original"))
        .filter(prazo_efetivo_calc__lte=limite)
        .select_related("responsavel", "comunicado")
    )
    for acao in acoes:
        _notificar_prazo(acao, acao.prazo_efetivo_calc)


def _notificar_prazo(acao, prazo):
    if not acao.responsavel or not acao.responsavel.email:
        return

    hoje = timezone.localdate()
    situacao = "atrasada" if prazo < hoje else f"vence em {(prazo - hoje).days} dia(s)"

    enviar_email(
        assunto=f"[CAI] Ação {situacao} - {acao.comunicado.cai_fiscal}",
        corpo=(
            f"A ação abaixo está {situacao}:\n\n"
            f"Comunicado: {acao.comunicado.cai_fiscal}\n"
            f"Descrição: {acao.descricao}\n"
            f"Prazo: {prazo.isoformat()}\n"
        ),
        destinatarios=[acao.responsavel.email],
    )
