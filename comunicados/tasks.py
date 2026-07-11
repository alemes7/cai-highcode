from celery import shared_task

from core.emails import enviar_email


@shared_task
def notificar_novo_comunicado(comunicado_id):
    """Avisa os departamentos que já têm Tarefa vinculada a este Comunicado.

    Assume que a view que cria o Comunicado também cria as Tarefas na mesma
    transação, antes do commit — o dispatch desta task é feito via
    transaction.on_commit() (ver comunicados/signals.py), então quando o
    worker efetivamente processar a task as Tarefas já devem existir.
    """
    from core.models import Departamento

    from .models import Comunicado

    comunicado = Comunicado.objects.select_related("departamento_solicitante").get(
        pk=comunicado_id
    )
    departamento_ids = comunicado.tarefas.values_list("departamento_id", flat=True).distinct()

    destinatarios = set()
    copia = set()
    for departamento in Departamento.objects.filter(id__in=departamento_ids):
        destinatarios.update(departamento.responsaveis.values_list("email", flat=True))
        copia.update(departamento.responsaveis_copia.values_list("email", flat=True))

    if not destinatarios:
        return

    enviar_email(
        assunto=f"[ECN] Novo comunicado aberto - {comunicado.cai_fiscal}",
        corpo=(
            f"Um novo Comunicado foi aberto ({comunicado.departamento_solicitante}).\n\n"
            f"Cliente: {comunicado.cliente}\n"
            f"Número: {comunicado.numero_projeto}\n"
        ),
        destinatarios=list(destinatarios),
        copia=list(copia),
    )


@shared_task
def notificar_comunicado_finalizado(comunicado_id):
    from .models import Comunicado

    comunicado = Comunicado.objects.select_related("solicitante").get(pk=comunicado_id)

    if not comunicado.solicitante or not comunicado.solicitante.email:
        return

    enviar_email(
        assunto=f"[ECN] Comunicado finalizado - {comunicado.cai_fiscal}",
        corpo=(
            f"O Comunicado {comunicado.cai_fiscal} foi finalizado "
            f"com o status: {comunicado.get_status_display()}.\n"
        ),
        destinatarios=[comunicado.solicitante.email],
    )
