from celery import shared_task

from core.emails import enviar_email


def _destinatarios_departamento(departamento):
    return list(departamento.responsaveis.values_list("email", flat=True))


def _copia_departamento(departamento):
    return list(departamento.responsaveis_copia.values_list("email", flat=True))


@shared_task
def notificar_nova_tarefa(tarefa_id):
    from .models import Tarefa

    tarefa = Tarefa.objects.select_related("comunicado", "departamento", "responsavel").get(
        pk=tarefa_id
    )

    if tarefa.responsavel and tarefa.responsavel.email:
        destinatarios = [tarefa.responsavel.email]
    else:
        destinatarios = _destinatarios_departamento(tarefa.departamento)

    copia = _copia_departamento(tarefa.departamento) + list(
        tarefa.emails_copia.values_list("email", flat=True)
    )

    if not destinatarios:
        return

    comunicado = tarefa.comunicado
    enviar_email(
        assunto=(
            f"[CAI] Nova tarefa - {comunicado.cai_fiscal} - "
            f"{tarefa.departamento}"
        ),
        corpo=(
            f"Uma nova tarefa foi atribuída ao departamento {tarefa.departamento} "
            f"no Comunicado {comunicado.cai_fiscal}.\n\n"
            f"Cliente: {comunicado.cliente}\n"
            f"Prazo: {tarefa.prazo.isoformat() if tarefa.prazo else '-'}\n"
        ),
        destinatarios=destinatarios,
        copia=copia,
    )


@shared_task
def notificar_tarefa_rejeitada(tarefa_id):
    from .models import Tarefa

    tarefa = Tarefa.objects.select_related("comunicado__solicitante", "departamento").get(
        pk=tarefa_id
    )
    comunicado = tarefa.comunicado

    if not comunicado.solicitante or not comunicado.solicitante.email:
        return

    enviar_email(
        assunto=f"[CAI] Comunicado rejeitado - {comunicado.cai_fiscal}",
        corpo=(
            f"O departamento {tarefa.departamento} rejeitou o Comunicado "
            f"{comunicado.cai_fiscal}.\n\n"
            f"Justificativa: {tarefa.justificativa or '-'}\n"
        ),
        destinatarios=[comunicado.solicitante.email],
    )
