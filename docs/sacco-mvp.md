# Institution and administrator MVP

## Administrator

Open `/admin/` and sign in using a superuser account. To create the first admin,
run `python manage.py createsuperuser` from the repository root with the virtual
environment activated. Never share this account with a SACCO representative.

1. In **SACCOs and banks**, open **Add institution**, choose the type and save its name.
2. In **Add a person**, open **Add user**, enter the name, phone and password,
   and choose Member, SACCO representative, Bank representative or Administrator.
3. For a representative, choose their SACCO. For a member, assigning a SACCO is optional.
4. Under Users, use **Manage an existing user's SACCO** to grant or remove
   representative access or update a member's institution. Leave SACCO empty to remove it.
5. Members enable sharing on their own Profile page. Changing membership requires fresh consent.
6. Delete users from the Users table. Review the confirmation: deletion removes associated
   records permanently. You cannot delete your own administrator account.

Disable a SACCO access record to revoke access immediately, including requests
made using an existing login token. Disable the user to disable all their logins.
For password help, verify identity and use the user's change-password action.

## SACCO representative

Use `/sacco/login/`, linked from the public navigation. Enter the approved account's
phone number and password. Successful login opens `/sacco/`. Unapproved users
receive no tokens from the SACCO login endpoint. Ordinary member login remains
available on the landing page, and approved representatives also route to SACCO
insights when logging in there.

Reports show only the assigned SACCO's active, consenting members. No member list,
individual balances or personal transactions are available to representatives.
Savings growth compares the two completed month ends. Cohorts and sector groups
need at least five members before reporting; a new installation will correctly
show insufficient data until there is enough consented history. Records are
self-reported, so these trends do not verify how loan funds were spent.

The administrator workspace at `/admin/` uses a simplified Jenga interface and Django session authentication. SACCOs have no Django
admin permission merely because they have SACCO access. There is no public role
selection or self-approval. SMS configuration, delivery code, endpoints and recovery
tables have been removed; historical migrations remain so existing databases can
upgrade safely.


## Banks, logins and the partner dropdown

Adding an institution creates its directory entry, not a shared login. After adding
it, open Add user, choose Bank representative or SACCO representative, select the
matching institution field and set a phone number and password. Both roles use
`/sacco/login/`, now labelled Institution login. Banks use the same report page,
with data scoped to their own assigned, consenting clients.

For an existing user, use Manage an existing user's institution. Choose Bank login
access or SACCO login access, then select the matching institution. Member's bank
and Member's SACCO assignments determine which clients contribute to reports.
Only representatives receive institution login access. Assigning a representative
to a bank through this workspace removes their previous SACCO representative grant,
and vice versa.

The user's Add Partner form fetches `/api/v1/institutions/` each time it opens.
Newly added banks and SACCOs appear automatically. Selecting one records account
terms with the administrator's institution name/type; it does not automatically
assign membership, enable sharing, or give the institution access to personal records.
Older manually entered partner accounts remain readable.

Admin logout ends the Django session and redirects to `/`. The workspace logout
also clears browser API tokens so the landing page does not restore that login.


Institution insights also shows **Members on Jenga**: the current number of enabled
user accounts assigned to that bank or SACCO by an administrator. This includes
members who have not opted into financial reporting and is not a measure of recent
login activity. The count appears even when there is insufficient savings history.
Financial trends still require consent and the existing minimum group size; no
individual member details or balances are exposed.
