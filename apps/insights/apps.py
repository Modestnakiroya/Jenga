from django.apps import AppConfig


class InsightsConfig(AppConfig):
    name = "apps.insights"

    def ready(self):
        from . import signals  # noqa: F401
