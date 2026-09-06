from django.conf import settings
from django.views.generic import TemplateView

from apps.accounts.models import BusinessType, Language, TrackingFrequency
from apps.assistant.translations import PageLabels, dashboard_labels_json
from apps.transactions.models import EXPENSE_CATEGORIES, INCOME_CATEGORIES, TransactionCategory

LANDING_LANGUAGE_SESSION_KEY = "landing_language"
LANDING_HTML_LANG = {
    "english": "en",
    "luganda": "lg",
    "runyankole": "nyn",
    "acholi": "ach",
    "ateso": "teo",
}


def resolve_landing_language(request):
    requested = (request.GET.get("language") or "").strip().lower()
    if requested in Language.values:
        request.session[LANDING_LANGUAGE_SESSION_KEY] = requested
        return requested
    cookie_name = getattr(settings, "SESSION_COOKIE_NAME", "sessionid")
    if cookie_name not in request.COOKIES:
        return Language.ENGLISH
    stored = (request.session.get(LANDING_LANGUAGE_SESSION_KEY) or "").strip().lower()
    if stored in Language.values:
        return stored
    return Language.ENGLISH


class TranslatedPageMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["dashboard_labels_json"] = dashboard_labels_json()
        return context


class HomeView(TranslatedPageMixin, TemplateView):
    template_name = "home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        landing_language = resolve_landing_language(self.request)
        context["business_types"] = BusinessType.choices
        context["tracking_frequencies"] = TrackingFrequency.choices
        context["languages"] = Language.choices
        context["landing_language"] = landing_language
        context["landing_html_lang"] = LANDING_HTML_LANG.get(landing_language, "en")
        context["landing_text"] = dict(PageLabels(landing_language))
        labels = dict(TransactionCategory.choices)
        context["income_categories"] = [
            (value, labels[value]) for value in INCOME_CATEGORIES
        ]
        context["expense_categories"] = [
            (value, labels[value]) for value in EXPENSE_CATEGORIES
        ]
        return context


class PartnershipsView(TranslatedPageMixin, TemplateView):
    template_name = "partnerships.html"


class ProfilePageView(TranslatedPageMixin, TemplateView):
    template_name = "profile.html"


class AssistantPageView(TranslatedPageMixin, TemplateView):
    template_name = "assistant.html"


class PartnersView(TranslatedPageMixin, TemplateView):
    template_name = "partners.html"


class InsightsPageView(TemplateView):
    template_name = "insights.html"


class SaccoPageView(TemplateView):
    template_name = "sacco.html"
