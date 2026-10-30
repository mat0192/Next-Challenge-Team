from copy import deepcopy
from datetime import date, timedelta
import json
import unittest

from core import fresh, allocation, save_portfolio, save_proposal, add_decision, validate, report
from storage import decode, encode


def position(ticker, qty, issuer=None):
    return dict(ticker=ticker, name=ticker, issuer=issuer or ticker, quantity=qty, sector="Technologie", kind="Action")


def quote(price=100, age=0, currency="EUR"):
    return dict(price=price, date=(date.today()-timedelta(days=age)).isoformat(), currency=currency, source="test")


def proposal():
    return dict(id="p1", author="Tim", name="Exemple", ticker="EX.PA", sector="Technologie", thesis="Hypothèse à vérifier",
                fundamentals="Résultats et valorisation", technical="Tendance", catalyst="Résultats prochains",
                risk="Baisse des marges", invalidation="Marge sous notre hypothèse", sources="Rapport annuel 2026",
                target_weight=4.0, bear=-15.0, base=5.0, bull=15.0, review_date=date.today().isoformat(),
                status="Prête pour le comité", ai_note="Sans IA")


class CoreTests(unittest.TestCase):
    def test_exact_boundaries(self):
        # 4*10% + 12*5%, fully invested. Exactly 5% is excluded.
        rows = [position(f"A{i}", 100 if i < 4 else 50) for i in range(16)]
        a = allocation(rows, 0, {p["ticker"]:quote() for p in rows})
        self.assertAlmostEqual(a["large_weight"], .4)
        self.assertEqual(a["alerts"], [])

    def test_six_equal_sector_positions_are_not_compliant(self):
        rows = [position(f"A{i}", 100) for i in range(6)]
        a = allocation(rows, 0, {p["ticker"]:quote() for p in rows})
        self.assertAlmostEqual(a["large_weight"], 1)
        self.assertEqual(len(a["alerts"]), 8)

    def test_small_crossing_of_five_percent_counts(self):
        rows = [position(f"A{i}", 51) for i in range(10)]
        a = allocation(rows, 49000, {p["ticker"]:quote() for p in rows})
        self.assertAlmostEqual(a["large_weight"], .51)
        self.assertTrue(any("40 %" in x for x in a["alerts"]))

    def test_same_issuer_is_aggregated(self):
        rows = [position("ONE", 60, "SAME"),position("TWO", 60, "SAME")]
        a = allocation(rows, 88000, {p["ticker"]:quote() for p in rows})
        self.assertAlmostEqual(a["largest"], .12)
        self.assertEqual(a["n_values"], 1)

    def test_missing_or_non_eur_never_yields_partial_total(self):
        rows = [position("ONE",10),position("TWO",10)]
        for quotes in ({"ONE":quote()}, {"ONE":quote(),"TWO":quote(currency="USD")}, {"ONE":quote(),"TWO":quote(float("nan"))}):
            with self.assertRaises(ValueError):
                allocation(rows, 1000, quotes)

    def test_stale_quotes_remain_explicit(self):
        a = allocation([position("ONE",10)],1000,{"ONE":quote(age=10)})
        self.assertEqual(a["stale"],["ONE"])

    def test_portfolio_is_independent_of_prices_and_proposals(self):
        initial = fresh()
        state = save_portfolio(initial,[position("ONE",20)],198000,date.today().isoformat(),"Relevé NextWise","Mathis")
        snapshot = deepcopy(state["portfolio"])
        allocation(snapshot["positions"],snapshot["cash"],{"ONE":quote(130)})
        with_proposal = save_proposal(state,proposal(),"Tim")
        decided = add_decision(with_proposal,"Mathis","Ne rien changer","Information insuffisante")
        self.assertEqual(decided["portfolio"],snapshot)
        self.assertEqual(initial,fresh())
        self.assertEqual(decided["revision"],3)

    def test_cash_quantities_and_duplicates(self):
        bad_rows = [[position("ONE",1.5)], [position("ONE",-1)], [position("ONE",1),position("ONE",2)]]
        for rows in bad_rows:
            with self.assertRaises(ValueError):
                save_portfolio(fresh(),rows,10,date.today().isoformat(),"Relevé","Mathis")
        with self.assertRaises(ValueError):
            save_portfolio(fresh(),[],-1,date.today().isoformat(),"Relevé","Mathis")

    def test_ready_proposal_requires_evidence(self):
        p = proposal()
        p["sources"] = ""
        with self.assertRaises(ValueError):
            save_proposal(fresh(),p,"Tim")
        p["status"] = "À étudier"
        self.assertEqual(len(save_proposal(fresh(),p,"Tim")["proposals"]),1)

    def test_validated_roundtrip_and_invalid_imports(self):
        state = save_proposal(fresh(),proposal(),"Tim")
        self.assertEqual(decode(encode(state)),state)
        malformed = [None, {}, {"schema":1}, {**fresh(),"portfolio":[]},
                     {**fresh(),"manual_quotes":{"ONE":[]}},
                     {**fresh(),"proposals":[{}]},
                     {**fresh(),"portfolio":{**fresh()["portfolio"],"positions":[None]}}]
        for bad in malformed:
            with self.assertRaises(ValueError):
                decode(json.dumps(bad).encode())
        self.assertIn("non saisi",report(fresh()))


if __name__ == "__main__":
    unittest.main()
