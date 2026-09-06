from django.apps import AppConfig


class SmsGatewayConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.sms_gateway"
    label = "sms_gateway"
    verbose_name = "SMS Gateway"
