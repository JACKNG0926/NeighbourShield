from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from core.views_web import admin_dashboard

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('core.urls')),  # We will build this next
    path('', admin_dashboard, name='dashboard'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)