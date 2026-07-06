from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("enhancer.urls")),
    path("accounts/", include("django.contrib.auth.urls")),
]


if settings.DEBUG:
    # Serve media uploads
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    # Serve static assets (helps when running without Django's static dev setup)
    urlpatterns += static(
        settings.STATIC_URL,
        document_root=(settings.BASE_DIR / "static" if hasattr(settings, "BASE_DIR") else None),
    )
