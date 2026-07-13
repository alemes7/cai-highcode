from functools import wraps

from django.core.exceptions import PermissionDenied


def admin_required(view_func):
    """Restringe a view a usuários com is_staff=True (reaproveita o mesmo flag
    do Django Admin — ver decisão registrada na conversa). Deve ser usado
    sempre DEPOIS de @login_required na pilha de decorators, para que um
    usuário não autenticado seja redirecionado ao login em vez de receber 403."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied("Acesso restrito a administradores.")
        return view_func(request, *args, **kwargs)

    return wrapper
