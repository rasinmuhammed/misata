"""Guard: generated email must match the person's name.

A mismatched name/email is the most obvious 'this data is fake' tell. This previously
slipped through on domains that use a single `name` column (SaaS, ecommerce) because the
fixer only handled split first_name/last_name columns. These tests lock in the fix.
"""
import warnings
import misata

warnings.filterwarnings("ignore")


def _email_matches_name(name: str, email: str) -> bool:
    local = email.split("@")[0].lower()
    tokens = [t for t in name.lower().replace(".", " ").split() if len(t) >= 3]
    # at least one 3+ char name token (prefix) must appear in the email local part
    return any(tok[:4] in local for tok in tokens)


def test_saas_email_matches_name():
    t = misata.generate("A SaaS company with 300 users", rows=300, seed=1)
    u = t["users"]
    assert "name" in u.columns and "email" in u.columns
    rate = sum(_email_matches_name(r["name"], r["email"])
               for r in u[["name", "email"]].to_dict("records")) / len(u)
    assert rate > 0.9, f"only {rate:.0%} of emails match the name"


def test_ecommerce_email_matches_name():
    t = misata.generate("An ecommerce store with 300 customers", rows=300, seed=2)
    c = t["customers"]
    if "email" not in c.columns or "name" not in c.columns:
        return
    rate = sum(_email_matches_name(r["name"], r["email"])
               for r in c[["name", "email"]].to_dict("records")) / len(c)
    assert rate > 0.9, f"only {rate:.0%} of emails match the name"


def test_email_coherence_is_deterministic():
    a = misata.generate("A SaaS company with 200 users", rows=200, seed=5)
    b = misata.generate("A SaaS company with 200 users", rows=200, seed=5)
    assert list(a["users"]["email"]) == list(b["users"]["email"])
