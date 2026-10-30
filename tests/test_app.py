from pathlib import Path
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from core import fresh, save_portfolio
from storage import hash_password
from datetime import date

APP = str(Path(__file__).resolve().parents[1] / "app.py")


class AppTests(unittest.TestCase):
    def test_all_empty_book_pages_render(self):
        at = AppTest.from_file(APP, default_timeout=20).run()
        self.assertFalse(at.exception)
        self.assertIn("Préparer",at.title[0].value)
        for page in ["Analyses","Portefeuille","Comité","Équipe & cadre","Code & automatisation"]:
            at.sidebar.radio[0].set_value(page).run()
            self.assertFalse(at.exception, page)
        self.assertEqual(at.session_state["book"]["portfolio"]["positions"],[])

    def test_create_analysis_and_keep_it_across_pages(self):
        at = AppTest.from_file(APP, default_timeout=20).run()
        at.sidebar.radio[0].set_value("Analyses").run()
        next(x for x in at.text_input if x.label == "Entreprise ou ETF").set_value("Exemple de test")
        next(x for x in at.text_area if x.label.startswith("Thèse en")).set_value("Hypothèse sourcée à compléter")
        next(x for x in at.button if x.label == "Enregistrer la fiche").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.session_state["book"]["proposals"]),1)
        at.sidebar.radio[0].set_value("Vue d’ensemble").run()
        at.sidebar.radio[0].set_value("Analyses").run()
        self.assertEqual(at.session_state["book"]["proposals"][0]["name"],"Exemple de test")

    def test_shared_mode_fails_closed_without_accounts(self):
        at = AppTest.from_file(APP)
        at.secrets["storage"] = {"backend":"github"}
        at.run()
        self.assertFalse(at.exception)
        self.assertTrue(at.error)
        self.assertEqual(len(at.sidebar.radio),0)

    def test_new_session_loads_shared_book_and_analyst_cannot_edit_cash(self):
        saved = save_portfolio(fresh(),[],187123.45,date.today().isoformat(),"Relevé vérifié","Mathis")
        password = "Phrase de passe pour les tests"
        digest = hash_password(password)
        with patch("storage.GitHubStore") as factory:
            factory.return_value.load.return_value = (saved,"revision-saved")
            at = AppTest.from_file(APP, default_timeout=20)
            at.secrets["storage"] = {"backend":"github","repository":"owner/repo","token":"test-placeholder"}
            at.secrets["users"] = {"tim":{"name":"Tim","role":"analyst","password_hash":digest}}
            at.run()
            factory.assert_not_called()
            at.text_input[0].set_value("tim")
            at.text_input[1].set_value(password)
            next(x for x in at.button if x.label == "Ouvrir l’espace").click().run()
            self.assertFalse(at.exception)
            self.assertEqual(at.session_state["book"]["portfolio"]["cash"],187123.45)
            at.sidebar.radio[0].set_value("Portefeuille").run()
            self.assertFalse(at.exception)
            self.assertFalse(any(x.label == "Enregistrer le portefeuille commun" for x in at.button))
            factory.return_value.save.assert_not_called()
