"""Team book: validation, allocation and durable, auditable mutations.

No function in this project places orders on NextWise.
"""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import math
import re
from uuid import uuid4

SECTORS = {"Technologie": "Tim", "Santé": "Sarah", "Finance": "Lucas",
           "Consommation": "Diane", "Industrie": "Layana", "Énergie": "Jade"}
RULES_URL = "https://www.nextwise.fr/le-reglement"
RULES_DATE = "2026-10-29"
STATUSES = ["À étudier", "Prête pour le comité", "À approfondir", "Retenue", "Écartée"]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fresh():
    return {"schema": 1, "revision": 0, "updated_at": None,
            "team": {"name": "NextChallenge · Équipe", "sectors": SECTORS.copy(),
                     "coordinator": "Mathis", "next_meeting": None},
            "portfolio": {"initialized": False, "cash": 200000.0, "positions": [],
                          "as_of": None, "note": ""},
            "manual_quotes": {}, "proposals": [], "meetings": [], "decisions": [], "audit": []}


def number(value, label, minimum=0):
    if isinstance(value, bool):
        raise ValueError(f"{label} : nombre attendu.")
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} : nombre attendu.") from None
    if not math.isfinite(n) or n < minimum:
        raise ValueError(f"{label} : nombre fini supérieur ou égal à {minimum} attendu.")
    return n


def clean_positions(rows):
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("Liste de positions invalide.")
    cleaned, seen = [], set()
    for row in rows:
        ticker = str(row.get("ticker", "")).strip().upper()
        if not ticker and not row.get("quantity"):
            continue
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9.^=\-]{0,23}", ticker):
            raise ValueError("Code de cotation absent ou invalide.")
        if ticker in seen:
            raise ValueError(f"{ticker} apparaît deux fois. Regroupez ses quantités.")
        seen.add(ticker)
        qty = number(row.get("quantity"), "Quantité")
        if qty != int(qty):
            raise ValueError("Les quantités doivent être entières.")
        if qty == 0:
            continue
        sector = str(row.get("sector", "Non classé"))
        if sector not in [*SECTORS, "ETF diversifié", "Autre", "Non classé"]:
            raise ValueError("Secteur inconnu.")
        cleaned.append({"ticker": ticker, "name": str(row.get("name") or ticker).strip()[:100],
                        "issuer": str(row.get("issuer") or ticker).strip().upper()[:100],
                        "quantity": int(qty), "sector": sector,
                        "kind": "ETF" if row.get("kind") == "ETF" else "Action"})
    if len(cleaned) > 100:
        raise ValueError("Maximum technique de 100 positions.")
    return cleaned


def validate(state):
    if not isinstance(state, dict) or type(state.get("schema")) is not int or state.get("schema") != 1:
        raise ValueError("Format de sauvegarde incompatible : version 1 attendue.")
    if type(state.get("revision")) is not int or state["revision"] < 0:
        raise ValueError("Révision de sauvegarde invalide.")
    try:
        p, team = state["portfolio"], state["team"]
        if not isinstance(p, dict) or not isinstance(team, dict):
            raise ValueError("Portefeuille ou équipe invalide.")
        if not all(isinstance(team[k], str) and team[k].strip() for k in ("name", "coordinator")):
            raise ValueError("Nom d’équipe ou coordination invalide.")
        if not isinstance(p["note"], str):
            raise ValueError("Note de portefeuille invalide.")
        if type(p["initialized"]) is not bool:
            raise ValueError("État du portefeuille invalide.")
        number(p["cash"], "Liquidités")
        if clean_positions(p["positions"]) != p["positions"]:
            raise ValueError("Positions non normalisées.")
        if p["as_of"]:
            date.fromisoformat(p["as_of"])
        if set(team["sectors"]) != set(SECTORS):
            raise ValueError("Les six secteurs doivent être présents.")
        if not all(isinstance(x, str) and x.strip() for x in team["sectors"].values()):
            raise ValueError("Responsable absent.")
        if team["next_meeting"]:
            date.fromisoformat(team["next_meeting"])
        if not isinstance(state.get("manual_quotes"), dict):
            raise ValueError("Cours manuels invalides.")
        for symbol, quote in state["manual_quotes"].items():
            if not isinstance(quote, dict):
                raise ValueError("Cours manuel invalide.")
            number(quote["price"], "Cours", 0.0000001)
            date.fromisoformat(quote["date"])
            if quote["currency"] != "EUR" or not isinstance(quote["source"], str):
                raise ValueError("Cours manuel non EUR ou sans source.")
        for key in ("proposals", "meetings", "decisions", "audit"):
            if not isinstance(state[key], list) or not all(isinstance(x, dict) for x in state[key]):
                raise ValueError("Journal invalide.")
        ids = []
        for proposal in state["proposals"]:
            ids.append(proposal["id"])
            validate_proposal(proposal)
        if len(ids) != len(set(ids)):
            raise ValueError("Fiches dupliquées.")
        for decision in state["decisions"]:
            for key in ("id", "at", "author", "reason", "action", "proposal_id"):
                if not isinstance(decision[key], str):
                    raise ValueError("Décision invalide.")
        for meeting in state["meetings"]:
            date.fromisoformat(meeting["date"])
            for key in ("id", "author", "participants", "minutes", "next_actions"):
                if not isinstance(meeting[key], str):
                    raise ValueError("Compte rendu invalide.")
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Sauvegarde incomplète : ne pas remplacer la base partagée.") from exc
    return state


def validate_proposal(p):
    for field in ("id", "author", "name", "ticker", "thesis", "fundamentals", "technical",
                  "catalyst", "risk", "invalidation", "sources", "ai_note", "review_date"):
        if not isinstance(p.get(field), str):
            raise ValueError(f"Champ de fiche invalide : {field}.")
    if not p["name"].strip() or not p["thesis"].strip():
        raise ValueError("L’entreprise et la thèse sont nécessaires.")
    if p.get("sector") not in SECTORS or p.get("status") not in STATUSES:
        raise ValueError("Secteur ou statut invalide.")
    date.fromisoformat(p["review_date"])
    if number(p.get("target_weight"), "Poids envisagé") > 100:
        raise ValueError("Poids envisagé supérieur à 100 %.")
    for key in ("bear", "base", "bull"):
        v = number(p.get(key), "Scénario", -100)
        if v > 1000:
            raise ValueError("Scénario supérieur à la limite technique de 1 000 %.")
    if not p["bear"] <= p["base"] <= p["bull"]:
        raise ValueError("Ordonnez les scénarios : défavorable ≤ central ≤ favorable.")
    if p["status"] in ["Prête pour le comité", "Retenue"]:
        missing = [k for k in ("sources", "risk", "invalidation", "fundamentals", "technical") if not p[k].strip()]
        if missing:
            raise ValueError("Avant le comité, complétez sources, risques, invalidation et analyses fondamentale/technique.")


def changed(state, actor, action):
    state["revision"] += 1
    state["updated_at"] = now()
    state["audit"].append({"at": state["updated_at"], "author": actor, "action": action})
    return validate(state)


def save_portfolio(state, rows, cash, as_of, note, actor):
    out = deepcopy(state)
    if not note.strip():
        raise ValueError("Indiquez l’origine du relevé ou la raison de la modification.")
    date.fromisoformat(as_of)
    if date.fromisoformat(as_of) > date.today():
        raise ValueError("Le relevé ne peut pas être daté dans le futur.")
    positions = clean_positions(rows)
    out["portfolio"] = {"initialized": True, "positions": positions,
                        "cash": number(cash, "Liquidités"), "as_of": as_of, "note": note}
    return changed(out, actor, "Portefeuille rapproché du relevé NextWise")


def save_proposal(state, proposal, actor):
    out = deepcopy(state)
    p = deepcopy(proposal)
    p["id"] = p.get("id") or str(uuid4())
    p["updated_at"] = now()
    validate_proposal(p)
    existing = next((i for i, x in enumerate(out["proposals"]) if x["id"] == p["id"]), None)
    if existing is None:
        out["proposals"].append(p)
    else:
        out["proposals"][existing] = p
    return changed(out, actor, "Fiche d’analyse enregistrée : " + p["name"])


def add_decision(state, actor, action, reason, proposal_id=""):
    if not reason.strip():
        raise ValueError("Expliquez la décision, y compris une décision de ne rien changer.")
    out = deepcopy(state)
    out["decisions"].append({"id": str(uuid4()), "at": now(), "author": actor,
                             "action": action, "reason": reason, "proposal_id": proposal_id})
    return changed(out, actor, "Décision du comité enregistrée")


def add_meeting(state, actor, meeting_date, participants, minutes, next_actions, next_date):
    if not participants.strip() or not minutes.strip():
        raise ValueError("Renseignez les participants et le compte rendu.")
    out = deepcopy(state)
    out["meetings"].append({"id": str(uuid4()), "date": meeting_date, "author": actor,
                            "participants": participants, "minutes": minutes, "next_actions": next_actions})
    out["team"]["next_meeting"] = next_date
    return changed(out, actor, "Compte rendu du comité enregistré")


def allocation(positions, cash, quotes):
    cash = number(cash, "Liquidités")
    rows, issuer_values, sectors, stale = [], {}, {}, []
    for p in clean_positions(positions):
        q = quotes.get(p["ticker"])
        if not q or q.get("currency") != "EUR":
            raise ValueError(f"{p['ticker']} : cours EUR absent. Total non calculé.")
        price = number(q.get("price"), "Cours", 0.0000001)
        quoted_date = date.fromisoformat(q["date"][:10])
        if quoted_date > date.today() or (date.today() - quoted_date).days > 7:
            stale.append(p["ticker"])
        value = p["quantity"] * price
        rows.append({**p, "price": price, "value": value, "date": q["date"]})
        issuer_values[p["issuer"]] = issuer_values.get(p["issuer"], 0) + value
        sectors[p["sector"]] = sectors.get(p["sector"], 0) + value
    total = cash + sum(x["value"] for x in rows)
    if total <= 0:
        raise ValueError("Valeur totale nulle : poids non calculables.")
    for row in rows:
        row["weight"] = row["value"] / total
    weights = {k: v / total for k, v in issuer_values.items()}
    large = sum(v for v in weights.values() if v > 0.05 + 1e-10)
    alerts = [f"{k} : {v:.1%}, au-dessus de 10 %." for k, v in weights.items() if v > 0.1 + 1e-10]
    if large > 0.4 + 1e-10:
        alerts.append(f"Les expositions de plus de 5 % totalisent {large:.1%} (plafond 40 %).")
    if len(weights) < 16:
        alerts.append(f"{len(weights)} valeurs : repère club de 16 à examiner.")
    if stale:
        alerts.append("Cours anciens ou datation incorrecte : " + ", ".join(stale))
    return {"total": total, "cash_weight": cash / total, "large_weight": large, "rows": rows,
            "sectors": {k: v / total for k, v in sectors.items()}, "alerts": alerts, "stale": stale,
            "n_values": len(weights), "largest": max(weights.values(), default=0)}


def report(state, quotes=None):
    validate(state)
    lines = [f"# {state['team']['name']}", f"Préparé le {now()}", "", "## À préparer pour le comité"]
    for sector, owner in state["team"]["sectors"].items():
        ps = [p for p in state["proposals"] if p["sector"] == sector]
        lines.append(f"- {sector} — {owner} : {len(ps)} fiche(s), "
                     f"{sum(p['status'] == 'Prête pour le comité' for p in ps)} prête(s).")
    lines.extend(["", "## Portefeuille", f"Relevé : {state['portfolio']['as_of'] or 'non saisi'}",
                  f"Liquidités saisies : {state['portfolio']['cash']:.2f} EUR"])
    if quotes is not None and state["portfolio"]["initialized"]:
        try:
            a = allocation(state["portfolio"]["positions"], state["portfolio"]["cash"], quotes)
            lines.append(f"Valorisation indicative : {a['total']:.2f} EUR")
            lines += ["- " + x for x in a["alerts"]]
        except ValueError as exc:
            lines.append(str(exc))
    lines += ["", "## Dernières décisions"]
    for d in state["decisions"][-5:]:
        lines.append(f"- {d['at'][:10]} — {d['action']} : {d['reason']}")
    lines += ["", "À vérifier sur NextWise : participation de chaque membre, sources, chats, quiz et outils.",
              "Aucun ordre ni message n’est envoyé par ce rapport."]
    return "\n".join(lines)
