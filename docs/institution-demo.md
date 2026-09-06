# Fictional institution demo

From the repository root with your virtual environment activated:

```powershell
python manage.py seed_institution_demo
```

This command requires DEBUG=True and a local database. It creates separate,
clearly labelled demo institutions; real institutions and members are unchanged.
Rerunning skips existing demo groups without resetting passwords or records.

Open `/sacco/login/` (Institution login):

| Demo account | Phone | Demo-only password |
| --- | --- | --- |
| SACCO representative | +447700900100 | JengaDemo2026! |
| Bank representative | +447700900200 | JengaDemo2026! |

These are public development credentials, not production accounts. Phone numbers
are fictional and no SMS is sent. Each institution has 18 enabled members: six
market vendors, six shop owners and six tailors. The representative is not counted
as a member. Members have unusable passwords and simulated sharing consent.

Each member has a savings goal and 181 days of simulated daily balances through
the day the command ran. Try the current month, the last seven days or yesterday
through today. All three sectors meet the five-member reporting threshold. Dates
outside the seeded history can correctly show insufficient data. The data is
fictional and does not represent bank deposits, real savings or real consent.
