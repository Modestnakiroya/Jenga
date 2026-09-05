import pprint
from pathlib import Path

from django.core.management.base import BaseCommand

from apps.assistant.sunbird_client import translate_text
from apps.assistant.translations import ENGLISH_LABELS, SUPPORTED_LANGUAGES


class Command(BaseCommand):
    help = (
        "Translate dashboard labels once via Sunbird SALT and optionally write "
        "apps/assistant/translations.py. Not used on page load."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--write",
            action="store_true",
            help="Overwrite translations.py with the fetched dictionary.",
        )

    def handle(self, *args, **options):
        labels = {"english": dict(ENGLISH_LABELS)}
        for language in SUPPORTED_LANGUAGES:
            if language == "english":
                continue
            translated = {}
            for key, english in ENGLISH_LABELS.items():
                value = translate_text(english, language)
                translated[key] = value
                self.stdout.write("%s.%s: %s" % (language, key, value.encode("unicode_escape").decode("ascii")))
            labels[language] = translated

        if options["write"]:
            path = Path(__file__).resolve().parents[2] / "translations.py"
            path.write_text(_render_module(labels), encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Wrote {path}"))
        else:
            self.stdout.write(pprint.pformat(labels, width=100))


def _render_module(labels):
    english = labels["english"]
    chunks = [
        "# Dashboard labels were translated once with Sunbird SALT (POST /tasks/nllb_translate)",
        "# and stored here so each page load stays local. Do not call Sunbird while rendering",
        "# the dashboard — that would add latency and cost for a fixed label set.",
        "# Assistant replies that already contain computed numbers are still translated live",
        "# per request in apps.assistant.sunbird_client.",
        "#",
        "# Refresh these strings with:",
        "#   python manage.py translate_dashboard_labels --write",
        "",
        "SUPPORTED_LANGUAGES = (\"english\", \"luganda\", \"runyankole\", \"acholi\", \"ateso\")",
        "",
        "ENGLISH_LABELS = {",
    ]
    for key, value in english.items():
        chunks.append(f"    {key!r}: {value!r},")
    chunks.append("}")
    chunks.append("")
    chunks.append("DASHBOARD_LABELS = {")
    for language in SUPPORTED_LANGUAGES:
        chunks.append(f"    {language!r}: {{")
        for key in english:
            chunks.append(f"        {key!r}: {labels[language][key]!r},")
        chunks.append("    },")
    chunks.append("}")
    chunks.append("")
    return "\n".join(chunks)
