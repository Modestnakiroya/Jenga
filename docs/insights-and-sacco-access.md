# AI insights and SACCO access

## Personal insights

Open **AI insights** from the dashboard or AI assistant, or visit `/insights/`.
Enter a hypothetical deposit amount, its currency and a period of 1–12 months.
The authenticated API `/api/v1/insights/personal/` reads only that user's goals
and partner accounts. It does not make deposits or move savings.

Projections use decimal arithmetic and simple interest. For annual rates:
`interest = deposit × rate / 100 × months / 12`. For monthly rates, the divisor
12 is omitted. The resulting balance is the deposit plus interest, rounded to
two decimal places. No compounding, fees, taxes, withdrawals or additional
deposits are included. Recorded goal balances are reported in UGX and are not
treated as available cash. The input currency filters account comparisons.

The highlighted account is the highest estimated gross return among the user's
recorded accounts that meet the deposit minimum and have verified, non-future
terms dated within 90 days. Missing or stale terms produce no recommendation.
This is not a live bank catalogue, a suitability assessment, or a promise of
returns. A superuser can verify account terms under **Partner accounts** in
Django admin after checking the institution's terms. Ordinary API clients
cannot set `terms_verified`.

Optional AI explanation sends only the generated general savings tips to the
existing configured AI provider. It does not receive account numbers, names,
phone numbers, goal names or balances. Calculations and comparison ranking are
performed by the server, not the model. If the provider is unavailable, the
calculated insights and tips still work. No new AI provider is required.

## Granting SACCO access

1. Sign in to `/admin/` with a Django **superuser**. Use
   `python manage.py createsuperuser` from the repository root if one is needed.
2. Create a **Sacco** record under Insights.
3. Under **Sacco access**, select an existing Jenga user, the SACCO, and enable
   `is_active`. Leave that user's `is_staff` and `is_superuser` off: SACCO access
   does not require admin permissions.
4. Under **Sacco memberships**, associate each real member with that SACCO.
   Free-text institution names entered under Partners do not establish membership.
5. Members must opt in themselves under **Profile → SACCO insights sharing**.
   This checkbox is read-only in Django admin; administrators cannot consent
   through the account edit form on a member's behalf.

Approved SACCO users use the normal phone/password login. The app sends them to
`/sacco/`. Profile responses expose a read-only role: `user`, `sacco`, or `admin`.
The grant is checked from the database on every SACCO API request, not trusted
from a submitted role or a stale token. Disabling or deleting the grant revokes
access immediately. Only superusers can manage SACCOs, grants and memberships.
Admin UI creation and password changes use Django's password-hashing forms.

## What SACCOs can see

`/api/v1/insights/sacco/` returns only the assigned SACCO's opted-in members'
aggregate trends. It does not accept member IDs, arbitrary date ranges or
sector filters. It returns neither names, phone numbers, account identifiers,
member lists, exact group balances nor individual records.

Reports compare the last two completed calendar month ends. The same cohort
must have a recorded baseline for both dates. At least **five** members are
required for growth, and each displayed business sector also needs at least
five members. Percentages are rounded to whole numbers. A zero earlier balance
has no percentage growth. Sector shares use only publishable sectors in their
denominator. Small groups are withheld rather than combined into an identifiable
“other” category. These controls reduce disclosure risk; this is not a formal
differential-privacy system and outputs should not be represented as guaranteed
anonymous data.

History starts at opt-in. Normal goal saves/deletes update that day's snapshot;
the latest known balance is carried forward when no change was recorded.
No history is backfilled. The reported measure is change in self-reported goal
balances (excluding abandoned goals), not actual bank deposits or interest.
Bulk database updates bypass model signals and should not be used to change
goal balances. A newly deployed system will legitimately show insufficient
history until two month-end baselines and the cohort threshold are available.

Withdrawal deletes the member's snapshots and excludes them immediately.
Changing/removing SACCO membership withdraws consent and deletes history, so a
new SACCO does not inherit earlier sharing permission. Already viewed aggregate
reports cannot be recalled.

## Password recovery

SMS recovery has been removed for the MVP. The password-reset API is unavailable.
A superuser must verify identity outside Jenga and use the user's **change password**
action in Django admin. Existing sessions expire when the password changes.

## Verification

Regression coverage lives in `apps/insights/tests.py`, with existing account and
page tests. Test suites can use an isolated in-memory SQLite database without
touching development records. Production-equivalent PostgreSQL verification and
live AI-provider checks are separate from mocked service tests.
