from django.urls import path

from apps.assistant.views import AskView

urlpatterns = [
    path("assistant/ask/", AskView.as_view(), name="assistant-ask"),
]
