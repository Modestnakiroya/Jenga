from django.urls import path

from apps.sms_gateway.views import IncomingSMSView

urlpatterns = [
    path("sms/incoming/", IncomingSMSView.as_view(), name="sms-incoming"),
]
