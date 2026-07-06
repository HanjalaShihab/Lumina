from django.apps import AppConfig


class EnhancerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "enhancer"

    def ready(self):
        import enhancer.signals  # noqa
