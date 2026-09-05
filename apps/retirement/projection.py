from decimal import Decimal, ROUND_HALF_UP

ASSUMED_ANNUAL_GROWTH_RATE = Decimal("0.08")
PROJECTION_DISCLAIMER = "This is an estimate, not a guarantee."


def calculate_retirement_projection(profile):
    """Project retirement funding from a RetirementProfile.

    Uses ordinary-annuity future-value math with annual compounding:

        n = desired_retirement_age - current_age
        PV = current_savings + existing_pension_balance
        FV_existing = PV * (1 + r)^n
        gap = desired_retirement_fund - FV_existing
        required_annual = gap / (((1 + r)^n - 1) / r)   if gap > 0 else 0
        required_monthly = required_annual / 12

    r is ASSUMED_ANNUAL_GROWTH_RATE (0.08). Monthly contribution is the
    annual amount split evenly across 12 months.
    """
    years_remaining = int(profile.desired_retirement_age) - int(profile.current_age)
    if years_remaining < 1:
        raise ValueError("Desired retirement age must be greater than current age.")

    rate = ASSUMED_ANNUAL_GROWTH_RATE
    present_value = Decimal(str(profile.current_savings)) + Decimal(
        str(profile.existing_pension_balance)
    )
    growth_factor = (Decimal("1") + rate) ** years_remaining
    future_value_existing = present_value * growth_factor
    gap = Decimal(str(profile.desired_retirement_fund)) - future_value_existing

    if gap <= 0:
        required_monthly = Decimal("0.00")
    else:
        annuity_factor = (growth_factor - Decimal("1")) / rate
        required_annual = gap / annuity_factor
        required_monthly = (required_annual / Decimal("12")).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    current_monthly = Decimal(str(profile.current_monthly_contribution))
    return {
        "years_remaining": years_remaining,
        "required_monthly_contribution": required_monthly,
        "on_track": current_monthly >= required_monthly,
    }
