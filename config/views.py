from django.views.generic import TemplateView

from apps.accounts.models import BusinessType, Language, TrackingFrequency
from apps.assistant.translations import dashboard_labels_json
from apps.transactions.models import EXPENSE_CATEGORIES, INCOME_CATEGORIES, TransactionCategory


class HomeView(TemplateView):
    template_name = "home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["business_types"] = BusinessType.choices
        context["tracking_frequencies"] = TrackingFrequency.choices
        context["languages"] = Language.choices
        labels = dict(TransactionCategory.choices)
        context["income_categories"] = [
            (value, labels[value]) for value in INCOME_CATEGORIES
        ]
        context["expense_categories"] = [
            (value, labels[value]) for value in EXPENSE_CATEGORIES
        ]
        context["dashboard_labels_json"] = dashboard_labels_json()
        return context


class PartnershipsView(TemplateView):
    template_name = "partnerships.html"


class ProfilePageView(TemplateView):
    template_name = "profile.html"


class AssistantPageView(TemplateView):
    template_name = "assistant.html"


class PartnersView(TemplateView):
    template_name = "partners.html"


class InsightsPageView(TemplateView):
    template_name = "insights.html"


class SaccoPageView(TemplateView):
    template_name = "sacco.html"
