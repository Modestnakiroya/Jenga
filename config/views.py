import json

from django.views.generic import TemplateView

from apps.accounts.models import BusinessType, Language, TrackingFrequency
from apps.assistant.translations import DASHBOARD_LABELS
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
        context["dashboard_labels_json"] = json.dumps(DASHBOARD_LABELS, ensure_ascii=True)
        return context
