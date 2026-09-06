"""AI chooses a savings amount; server arithmetic bounds it to recorded surplus."""
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation

from django.core.cache import cache
from django.utils import timezone
from apps.assistant.llm import call_llm, LLMError
from apps.transactions.services import calculate_financial_summary
from apps.goals.models import Goal
from .decision_engine import calculate_safe_to_spend


def savings_advice(user, period):
    summary = calculate_financial_summary(user, period, timezone.localdate())
    cash = calculate_safe_to_spend(user)
    # Reserve known upcoming bills, but do not prescribe a fixed savings percentage.
    limit = max(Decimal(0), min(summary['estimated_profit'], cash['cash_on_hand'] - cash['upcoming_expenses']))
    facts = {
        'period': period, 'start': str(summary['period_start']), 'end': str(summary['period_end']),
        'income': str(summary['total_income']), 'expenses': str(summary['total_expenses']),
        'recorded_cash_surplus': str(cash['cash_on_hand']), 'upcoming_bills': str(cash['upcoming_expenses']),
        'maximum_recommendation': str(limit),
        'goals': [{'remaining': str(max(Decimal(0), g.target_amount-g.current_saved_amount)),
                   'deadline': str(g.target_date) if g.target_date else None, 'type': g.goal_type}
                  for g in Goal.objects.filter(user=user, status='active')],
    }
    if not summary['transaction_count']:
        return {'amount': None, 'status': 'needs_data', 'explanation': 'Record income and expenses to get an AI savings recommendation.'}
    encoded = json.dumps(facts, sort_keys=True)
    key = 'savings-advice:' + str(user.pk) + ':' + hashlib.sha256(encoded.encode()).hexdigest()
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        raw = call_llm(
            'You help a small business plan savings in UGX. Choose a prudent amount to save now from the selected period surplus, considering bills and goals. '
            'Leave room for unrecorded living/business costs. Recorded cash is only an estimate, not a bank balance. '
            'Do not use a fixed percentage. Return ONLY JSON with amount (decimal string, nonnegative, at most maximum_recommendation, up to 2 decimals) '
            'and explanation (two short plain sentences explaining the choice). Do not invent facts, promise returns or instruct a transfer.', encoded)
        # Models occasionally wrap valid JSON in a markdown fence or a short preface.
        candidate = str(raw).strip()
        fenced = re.search(r"\{.*\}", candidate, flags=re.DOTALL)
        data = json.loads(fenced.group(0) if fenced else candidate)
        amount = Decimal(str(data['amount']))
        explanation = data['explanation']
        if not amount.is_finite() or amount < 0 or amount > limit or amount != amount.quantize(Decimal('.01')):
            raise ValueError('Invalid amount')
        if not isinstance(explanation, str) or not explanation.strip() or len(explanation) > 1000:
            raise ValueError('Invalid explanation')
        result = {'amount': f'{amount:.2f}', 'status': 'ai', 'explanation': explanation.strip()}
        cache.set(key, result, 300)
        return result
    except (LLMError, ValueError, KeyError, TypeError, InvalidOperation):
        # Never disguise a formula or a provider failure as AI advice.
        return {'amount': None, 'status': 'unavailable', 'explanation': 'AI savings advice is unavailable right now. Please try again shortly.'}
