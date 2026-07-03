from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from acoes.services import cancelar_acoes_pendentes_do_comunicado
from comunicados.models import StatusComunicado
from comunicados.services import atualizar_status_comunicado
from comunicados.tasks import notificar_comunicado_finalizado

from .models import StatusTarefa, Tarefa
from .tasks import notificar_nova_tarefa, notificar_tarefa_rejeitada


@receiver(pre_save, sender=Tarefa)
def guardar_status_anterior(sender, instance, **kwargs):
    if instance.pk:
        instance._status_anterior = (
            Tarefa.objects.filter(pk=instance.pk).values_list("status", flat=True).first()
        )
    else:
        instance._status_anterior = None


@receiver(post_save, sender=Tarefa)
def ao_salvar_tarefa(sender, instance, created, **kwargs):
    if created:
        transaction.on_commit(lambda: notificar_nova_tarefa.delay(instance.pk))
        return

    status_anterior = getattr(instance, "_status_anterior", None)
    if status_anterior == instance.status:
        return

    if instance.status == StatusTarefa.REJEITADO:
        cancelar_acoes_pendentes_do_comunicado(instance.comunicado)
        transaction.on_commit(lambda: notificar_tarefa_rejeitada.delay(instance.pk))

    mudou = atualizar_status_comunicado(instance.comunicado)
    if mudou and instance.comunicado.status != StatusComunicado.PENDENTE:
        comunicado_id = instance.comunicado_id
        transaction.on_commit(lambda: notificar_comunicado_finalizado.delay(comunicado_id))
