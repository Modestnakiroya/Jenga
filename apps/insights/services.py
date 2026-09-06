from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.utils import timezone

from apps.accounts.models import BusinessType, User
from apps.goals.models import Goal
from .models import SavingsSnapshot

MIN_COHORT = 5


def money(value):
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def personal_insights(user, amount, currency, months):
    today = timezone.localdate()
    goals = list(Goal.objects.filter(user=user).exclude(status="abandoned").order_by("target_date", "id"))
    total = sum((g.current_saved_amount for g in goals), Decimal(0))
    targets = sum((g.target_amount for g in goals), Decimal(0))
    goal_facts = []
    for goal in goals:
        remaining = max(Decimal(0), goal.target_amount - goal.current_saved_amount)
        days = (goal.target_date - today).days if goal.target_date else None
        goal_facts.append({"name": goal.name, "remaining": money(remaining), "progress_percent": str(goal.progress_percentage),
                           "target_date": goal.target_date.isoformat() if goal.target_date else None,
                           "daily_saving_to_target": money(remaining / days) if days and days > 0 else None})
    accounts = []
    for account in user.partner_accounts.filter(currency=currency):
        rate = account.interest_rate
        minimum = account.minimum_deposit
        eligible = minimum is not None and amount >= minimum
        fresh = bool(account.terms_updated_on and today - timedelta(days=90) <= account.terms_updated_on <= today)
        valid_rate = rate is not None and Decimal(0) <= rate <= Decimal(100)
        interest = amount * rate / 100 * months / (12 if account.interest_period == "annual" else 1) if valid_rate else None
        accounts.append({"id": account.pk, "institution": account.institution_name, "type": account.institution_type,
                         "account": account.account_name, "minimum_deposit": money(minimum) if minimum is not None else None,
                         "meets_minimum": eligible, "interest_rate": str(rate) if valid_rate else None,
                         "interest_period": account.interest_period, "terms_verified": account.terms_verified,
                         "terms_recent": fresh, "estimated_interest": money(interest) if interest is not None else None,
                         "estimated_balance": money(amount + interest) if interest is not None else None})
    comparable = [a for a in accounts if a["meets_minimum"] and a["terms_verified"] and a["terms_recent"] and a["estimated_interest"] is not None]
    best = max(comparable, key=lambda a: Decimal(a["estimated_interest"])) if comparable else None
    suggestions = []
    if not goals:
        suggestions.append("Add a savings goal so you can track progress toward a specific target.")
    if any(g.target_date and g.target_date <= today and g.current_saved_amount < g.target_amount for g in goals):
        suggestions.append("A goal's target date has arrived with a balance still to save. Review its target or contribution plan.")
    if goals and not any(g.goal_type == "emergency_fund" for g in goals):
        suggestions.append("Consider a separate emergency savings goal before locking money away.")
    if not comparable:
        suggestions.append("No account has all the recently verified terms needed for a recommendation. Confirm the interest period and minimum deposit with your institution.")
    suggestions.append("Keep money needed for upcoming expenses accessible. Check withdrawal rules, fees and taxes before moving savings.")
    return {"currency": currency, "amount": money(amount), "months": months, "savings_currency": "UGX",
            "saved_in_goals": money(total), "goal_targets": money(targets), "goals": goal_facts, "accounts": accounts,
            "recommended_account_id": best["id"] if best else None,
            "recommendation_basis": "Highest estimated gross interest among your recorded accounts with verified terms dated within 90 days and a minimum deposit you meet. Not a comparison of the whole market or a suitability assessment.",
            "assumptions": "One deposit held for the entire period; simple interest, with annual rates divided by 12. No compounding, extra deposits, withdrawals, fees or taxes. Rates assumed unchanged. Estimates are not guaranteed returns. Goal balances are self-reported, not available bank cash.",
            "suggestions": suggestions}


def reporting_months():
    """Use completed calendar months so partial months are not compared with full ones."""
    end = timezone.localdate().replace(day=1) - timedelta(days=1)
    months = []
    for _ in range(24):
        months.append({"value": end.strftime("%Y-%m"), "label": end.strftime("%B %Y")})
        end = end.replace(day=1) - timedelta(days=1)
    return months


def sacco_report(sacco, bank=False, month=None, start_date=None, end_date=None):
    # Date selection changes the snapshot cutoff, never the institution membership scope.
    end = timezone.localdate().replace(day=1) - timedelta(days=1)
    if month:
        from datetime import date
        year, number = map(int, month.split("-"))
        next_month = date(year + (number == 12), 1 if number == 12 else number + 1, 1)
        end = next_month - timedelta(days=1)
    previous_end = end.replace(day=1) - timedelta(days=1)
    if start_date is not None:
        # Carry the last known balance forward; missing pre-range history is not zero.
        previous_end = start_date - timedelta(days=1)
        end = end_date
    scope = {"bank_membership__bank": sacco} if bank else {"sacco_membership__sacco": sacco}
    member_count = User.objects.filter(**scope, is_active=True).count()
    users = list(User.objects.filter(**scope, share_sacco_insights=True, is_active=True).select_related("business_profile"))
    snapshots = SavingsSnapshot.objects.filter(user__in=users, date__lte=end).order_by("date", "pk")
    previous, current = {}, {}
    for row in snapshots:
        current[row.user_id] = row.amount
        if row.date <= previous_end:
            previous[row.user_id] = row.amount
    paired = [u for u in users if u.pk in previous and u.pk in current]
    result = {"sacco": sacco.name, "period_end": end.isoformat(), "previous_period_end": previous_end.isoformat(),
              "selected_month": end.strftime("%Y-%m"), "available_months": reporting_months(),
              "start_date": (start_date or (previous_end + timedelta(days=1))).isoformat(),
              "end_date": end.isoformat(), "today": timezone.localdate().isoformat(),
              "member_count": member_count,
              "member_count_description": "Enabled Jenga accounts assigned to your institution. Includes members who have not opted into financial insights; does not measure recent logins.",
              "minimum_group_size": MIN_COHORT, "growth_percent": None, "sectors": [],
              "method": "Change in recorded goal balances over the selected period for the same opted-in members. Not deposit flows or verified bank balances. Groups below five are withheld; percentages rounded to whole numbers. No personal records or exact balances are returned."}
    if len(paired) < MIN_COHORT:
        result["status"] = "Not enough opted-in members with history before and through this period. Collection starts when members opt in."
        return result
    old = sum((previous[u.pk] for u in paired), Decimal(0))
    new = sum((current[u.pk] for u in paired), Decimal(0))
    if old > 0:
        result["growth_percent"] = str(((new - old) / old * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    result["status"] = "Growth unavailable when the earlier balance is zero." if old == 0 else "Report available."
    grouped = {}
    for user in paired:
        profile = getattr(user, "business_profile", None)
        if profile:
            grouped.setdefault(profile.business_type, []).append(current[user.pk])
    visible = [(sector, values) for sector, values in grouped.items() if len(values) >= MIN_COHORT]
    total = sum((sum(values) for _, values in visible), Decimal(0))
    labels = dict(BusinessType.choices)
    for sector, values in sorted(visible, key=lambda pair: sum(pair[1]), reverse=True):
        # Shares are among publishable sectors only; no hidden-sector total can be subtracted.
        result["sectors"].append({"sector": labels.get(sector, sector), "share_of_visible_savings_percent": str((sum(values) / total * 100).quantize(Decimal("1"))) if total else None})
    return result
