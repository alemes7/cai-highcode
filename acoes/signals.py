from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Acao
from .tasks import notificar_nova_acao


@receiver(post_save, sender=Acao)
def ao_criar_acao(sender, instance, created, **kwargs):
    if created:
        transaction.on_commit(lambda: notificar_nova_acao.delay(instance.pk))
