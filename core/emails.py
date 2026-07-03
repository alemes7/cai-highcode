from django.conf import settings
from django.core.mail import EmailMessage


def enviar_email(assunto, corpo, destinatarios, copia=None):
    destinatarios = [e for e in destinatarios if e]
    if not destinatarios:
        return

    EmailMessage(
        subject=assunto,
        body=corpo,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=destinatarios,
        cc=[e for e in (copia or []) if e],
    ).send(fail_silently=False)
