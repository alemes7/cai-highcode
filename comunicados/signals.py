from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Comunicado
from .tasks import notificar_novo_comunicado


@receiver(post_save, sender=Comunicado)
def ao_criar_comunicado(sender, instance, created, **kwargs):
    if created:
        transaction.on_commit(lambda: notificar_novo_comunicado.delay(instance.pk))
