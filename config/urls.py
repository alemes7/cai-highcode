from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from core.views import media_privado

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    # Servido por view autenticada (não pelo helper static() do Django, que não
    # exige login) — anexos de Comunicados/Tarefas/Ações são documentos internos.
    path('media/<path:path>', media_privado, name='media_privado'),
    path('', include('core.urls')),
    path('comunicados/', include('comunicados.urls')),
    path('tarefas/', include('tarefas.urls')),
    path('acoes/', include('acoes.urls')),
]
