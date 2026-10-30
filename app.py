from copy import deepcopy
from datetime import date, timedelta
import json
import time

import pandas as pd
import streamlit as st
from core import (SECTORS, STATUSES, RULES_DATE, RULES_URL, fresh, changed, allocation,
                  save_portfolio, save_proposal, add_decision, add_meeting, report)
from market import fetch_quotes
from storage import GitHubStore, StorageError, ConflictError, encode, decode, verify_password

st.set_page_config(page_title="NextChallenge · Équipe", page_icon="◈", layout="wide")
st.markdown("""<style>
html,body,[class*='css'],[data-testid='stApp'] {font-family:'DM Sans',sans-serif}
.stApp {background:#f5f6f1;color:#142b35}
h1,h2,h3 {font-family:'Manrope',sans-serif!important;letter-spacing:-.035em}
h1 {font-weight:800!important} h3 {font-size:1.2rem!important}
[data-testid='stSidebar'] {background:#112e39;color:#f6f7f0}
[data-testid='stSidebar'] p,[data-testid='stSidebar'] label,[data-testid='stSidebar'] span {color:#f1f4ef}
[data-testid='stSidebar'] [data-testid='stRadio'] label {padding:.3rem 0}
[data-testid='stMetric'] {background:#fff;border:1px solid #dfe7dd;border-radius:14px;padding:18px}
[data-testid='stMetricValue'] {font-family:'Manrope',sans-serif;font-size:1.9rem}
[data-testid='stVerticalBlockBorderWrapper'] {border-radius:14px}
.block-container {max-width:1380px;padding-top:2.4rem;padding-bottom:3rem}
.eyebrow {color:#647c68;font-size:.77rem;letter-spacing:.16em;font-weight:700}
.stButton button[kind='primary'],.stFormSubmitButton button[kind='primary'] {background:#c5e86c;color:#142b35;border:0}
.stButton button,.stFormSubmitButton button {border-radius:9px;min-height:2.5rem}
</style>""", unsafe_allow_html=True)

try:
    config = st.secrets.to_dict()
except FileNotFoundError:
    config = {}
backend = config.get("storage", {}).get("backend", "demo")
if backend not in ("demo", "github"):
    st.error("Configuration de stockage inconnue. Aucun portefeuille n’a été chargé.")
    st.stop()
shared = backend == "github"
users = config.get("users", {})

if shared:
    if not users or any(not u.get("password_hash") or u.get("role") not in ("editor", "analyst") for u in users.values()):
        st.error("Configurez les comptes d’équipe dans les secrets avant d’ouvrir les données partagées.")
        st.stop()
    if "identity" not in st.session_state:
        st.markdown("<div class='eyebrow'>NEXTCHALLENGE / ESPACE ÉQUIPE</div>", unsafe_allow_html=True)
        st.title("Un portefeuille. Une équipe.")
        st.write("Connectez-vous avec votre compte d’équipe pour retrouver vos analyses et décisions.")
        with st.form("login"):
            username = st.text_input("Identifiant")
            password = st.text_input("Phrase de passe", type="password")
            submitted = st.form_submit_button("Ouvrir l’espace", type="primary")
        if submitted:
            until = st.session_state.get("retry_after", 0)
            if time.time() < until:
                st.error("Patientez quelques secondes avant un nouvel essai.")
            else:
                user = users.get(username.strip().lower(), {})
                if verify_password(password, user.get("password_hash", "")):
                    st.session_state.identity = username.strip().lower()
                    st.rerun()
                else:
                    st.session_state.retry_after = time.time() + 5
                    st.error("Identifiant ou phrase de passe incorrect.")
        st.stop()
    identity = st.session_state.identity
    if identity not in users:
        st.session_state.clear()
        st.rerun()
    actor = users[identity].get("name", identity)
    can_edit = users[identity]["role"] == "editor"
    try:
        store = GitHubStore(config["storage"]["repository"], config["storage"]["token"],
                            config["storage"].get("branch", "team-data"))
    except (KeyError, StorageError):
        st.error("Connexion au dépôt incomplète. Consultez le démarrage dans le README.")
        st.stop()
else:
    actor, identity, can_edit, store = "Mathis", "demo", True, None


def reload_book():
    try:
        if shared:
            book, sha = store.load()
        else:
            book, sha = fresh(), None
        st.session_state.book, st.session_state.sha = book, sha
        st.session_state.pop("pending_draft", None)
    except StorageError as exc:
        st.error(str(exc))
        st.stop()


if "book" not in st.session_state:
    reload_book()
book = st.session_state.book


def persist(candidate):
    try:
        sha = store.save(candidate, st.session_state.sha) if shared else None
    except (StorageError, ConflictError) as exc:
        st.error(str(exc))
        st.session_state.pending_draft = encode(candidate)
        return False
    st.session_state.book, st.session_state.sha = candidate, sha
    st.session_state.pop("pending_draft", None)
    st.session_state.flash = "Enregistré pour toute l’équipe." if shared else "Enregistré dans cette session de démonstration."
    st.rerun()


def attempt(function, *args):
    try:
        persist(function(*args))
    except (ValueError, TypeError) as exc:
        st.error(str(exc))


@st.cache_data(ttl=900, show_spinner=False)
def prices(tickers):
    return fetch_quotes(tickers)


def get_valuation():
    tickers = tuple(p["ticker"] for p in book["portfolio"]["positions"])
    if tickers:
        with st.spinner("Lecture des derniers cours disponibles…"):
            live, errors = prices(tickers)
    else:
        live, errors = {}, []
    quotes = {**book["manual_quotes"], **live}
    for error in errors:
        st.caption(error)
    used_manual = [t for t in tickers if t not in live and t in quotes]
    if used_manual:
        st.warning("Cours de secours saisis par l’équipe : " + ", ".join(used_manual))
    try:
        return allocation(book["portfolio"]["positions"], book["portfolio"]["cash"], quotes), quotes
    except ValueError as exc:
        st.warning(str(exc))
        return None, quotes


with st.sidebar:
    st.markdown("## ◈ NEXTCHALLENGE")
    st.caption("L’ATELIER DE L’ÉQUIPE")
    page = st.radio("Navigation", ["Vue d’ensemble", "Analyses", "Portefeuille", "Comité", "Équipe & cadre", "Code & automatisation"], label_visibility="collapsed")
    st.divider()
    st.write(f"**{actor}** · {'coordination' if can_edit else 'analyste'}")
    if shared:
        st.caption(f"Base commune · révision {book['revision']}")
        if st.button("Recharger les données d’équipe", width="stretch"):
            reload_book()
            st.rerun()
        st.caption("Rechargez avant de commencer une saisie. Les écritures concurrentes sont protégées.")
        if st.button("Se déconnecter"):
            st.session_state.clear()
            st.rerun()
    else:
        st.caption("Mode démonstration · données temporaires")
    st.link_button("Règlement officiel ↗", RULES_URL, width="stretch")

if not shared:
    st.info("DÉMONSTRATION — Vous pouvez essayer tous les écrans. Les saisies sont temporaires : exportez-les avant de fermer. Le mode partagé doit être configuré pour travailler à plusieurs.")
if st.session_state.get("flash"):
    st.success(st.session_state.pop("flash"))
if "pending_draft" in st.session_state:
    st.warning("Une sauvegarde a échoué. Conservez votre brouillon avant de recharger ; ne l’importez pas sur la base partagée sans comparer les changements.")
    st.download_button("Télécharger mon brouillon non enregistré", st.session_state.pending_draft, "brouillon-equipe.json", "application/json")


def header(kicker, title, description):
    st.markdown(f"<div class='eyebrow'>{kicker}</div>", unsafe_allow_html=True)
    st.title(title)
    st.write(description)


if page == "Vue d’ensemble":
    header("01 / PILOTAGE", "Préparer de meilleures décisions.", "Des analyses que chacun comprend, un portefeuille commun et une trace de vos choix.")
    cols = st.columns(4)
    cols[0].metric("Secteurs suivis", "6")
    cols[1].metric("Fiches prêtes", sum(p["status"] == "Prête pour le comité" for p in book["proposals"]))
    cols[2].metric("Décisions consignées", len(book["decisions"]))
    cols[3].metric("Prochain comité", date.fromisoformat(book["team"]["next_meeting"]).strftime("%d/%m") if book["team"]["next_meeting"] else "À fixer")
    st.write("")
    left, right = st.columns([1.65, 1], gap="large")
    with left:
        st.subheader("Votre prochaine étape")
        if not book["portfolio"]["initialized"]:
            st.warning("Le portefeuille d’équipe n’a pas encore été renseigné. Les 200 000 € sont la dotation de départ, pas un relevé de votre compte.")
        steps = [("1", "Cadrer le capital", "Lire les limites du club dans Équipe & cadre, puis relever les positions réelles sur NextWise."),
                 ("2", "Construire les propositions", "Chaque responsable remplit une fiche avec sources, scénarios et raisons de revoir son idée."),
                 ("3", "Décider ensemble", "Tous les 14 jours : examiner les risques, retenir ou reporter les propositions et noter pourquoi."),
                 ("4", "Rapprocher le portefeuille", "Après exécution sur NextWise, reporter les quantités et le cash. Actualiser les cours suffit entre deux opérations.")]
        for n, title, description in steps:
            with st.container(border=True):
                st.markdown(f"**{n.zfill(2)} · {title}**")
                st.caption(description)
    with right:
        st.subheader("À mettre à l’ordre du jour")
        overdue = [p for p in book["proposals"] if p["status"] != "Écartée" and p["review_date"] <= date.today().isoformat()]
        if overdue:
            for p in overdue:
                st.write(f"• {p['name']} — revue prévue le {p['review_date']}")
        else:
            st.caption("Aucune fiche à revoir aujourd’hui.")
        st.markdown("**Questions du comité**")
        st.write("Qu’est-ce qui a changé depuis notre dernière décision ? Quelle information contredirait notre thèse ? Quel risque prenons-nous ensemble ?")
        st.markdown("**La règle utile**")
        st.write("Une nouvelle analyse ne crée pas une obligation d’achat. « Conserver » et « attendre » sont aussi des décisions à documenter.")
    st.subheader("Six secteurs, six responsables")
    for offset in (0, 3):
        for col, (sector, owner) in zip(st.columns(3), list(book["team"]["sectors"].items())[offset:offset+3]):
            with col, st.container(border=True):
                st.markdown(f"**{sector}**")
                st.write(owner)
                count = sum(p["sector"] == sector for p in book["proposals"])
                st.caption(f"{count} fiche(s) d’analyse")

elif page == "Analyses":
    header("02 / RECHERCHE", "Une idée doit pouvoir se défendre.", "Le formulaire sépare les faits, les hypothèses et ce qui vous ferait changer d’avis.")
    sector_filter = st.selectbox("Filtrer les fiches", ["Tous les secteurs", *SECTORS])
    visible = [p for p in book["proposals"] if sector_filter == "Tous les secteurs" or p["sector"] == sector_filter]
    for p in visible:
        with st.expander(f"{p['name']} · {p['sector']} · {p['status']}"):
            st.caption(f"Auteur : {p['author']} · Revue : {p['review_date']} · Poids envisagé : {p['target_weight']:.1f} %")
            st.write(p["thesis"])
            a, b = st.columns(2)
            with a:
                st.markdown("**Faits et valorisation**")
                st.write(p["fundamentals"] or "À compléter")
                st.markdown("**Lecture technique**")
                st.write(p["technical"] or "À compléter")
                st.markdown("**Catalyseur**")
                st.write(p["catalyst"] or "À compléter")
            with b:
                st.markdown("**Risque et invalidation**")
                st.write(p["risk"] or "À compléter")
                st.write(p["invalidation"] or "À compléter")
                st.write(f"Scénarios : {p['bear']:+.1f} % / {p['base']:+.1f} % / {p['bull']:+.1f} %")
                st.caption("Hypothèses de l’auteur, sans probabilité ni rendement garanti.")
            st.markdown("**Sources et assistance IA**")
            st.write(p["sources"] or "Aucune source")
            st.write(p["ai_note"] or "Assistance IA non renseignée")
    if not visible:
        st.info("Aucune analyse pour le moment. ASML et Dassault Systèmes étaient vos exemples, pas des achats décidés : aucune position n’a été créée.")
    editable = [p for p in book["proposals"] if can_edit or p["author"] == actor]
    ids = ["new"] + [p["id"] for p in editable]
    labels = {p["id"]: p["name"] for p in editable}
    selected = st.selectbox("Créer ou modifier une fiche", ids, format_func=lambda x: "Nouvelle fiche" if x == "new" else labels[x])
    original = next((p for p in editable if p["id"] == selected), {})
    with st.form("proposal_" + selected):
        a, b, c = st.columns(3)
        name = a.text_input("Entreprise ou ETF", original.get("name", ""))
        ticker = b.text_input("Code Yahoo (ex. ASML.AS)", original.get("ticker", ""))
        sector = c.selectbox("Secteur", list(SECTORS), index=list(SECTORS).index(original.get("sector", "Technologie")))
        thesis = st.text_area("Thèse en trois phrases : pourquoi cet actif, pourquoi maintenant ?", original.get("thesis", ""))
        a, b = st.columns(2)
        fundamental = a.text_area("Analyse fondamentale : activité, résultats, valorisation", original.get("fundamentals", ""))
        technical = b.text_area("Analyse technique : tendance, niveaux, limites", original.get("technical", ""))
        catalyst = st.text_input("Catalyseur attendu et date", original.get("catalyst", ""))
        risk = a.text_area("Principaux risques", original.get("risk", ""))
        invalidation = b.text_area("Ce qui invaliderait la thèse", original.get("invalidation", ""))
        sources = st.text_area("Sources datées : liens vers publications, résultats, document ETF…", original.get("sources", ""))
        cols = st.columns(4)
        weight = cols[0].number_input("Poids envisagé (%)", 0.0, 100.0, float(original.get("target_weight", 0)), .5)
        bear = cols[1].number_input("Défavorable (%)", -100.0, 1000.0, float(original.get("bear", -15)), 1.0)
        base = cols[2].number_input("Central (%)", -100.0, 1000.0, float(original.get("base", 0)), 1.0)
        bull = cols[3].number_input("Favorable (%)", -100.0, 1000.0, float(original.get("bull", 15)), 1.0)
        st.caption("Scénarios illustratifs modifiables ; ils ne prédisent pas le marché. Le poids envisagé ne modifie pas le portefeuille.")
        a, b = st.columns(2)
        review = a.date_input("Prochaine revue de la thèse", date.fromisoformat(original["review_date"]) if original else date.today() + timedelta(days=14))
        allowed_status = STATUSES if can_edit else STATUSES[:3]
        existing_status = original.get("status", STATUSES[0])
        if not can_edit and existing_status in ("Retenue", "Écartée"):
            status = existing_status
            b.caption("Statut fixé par le comité : " + status)
        else:
            status = b.selectbox("Avancement", allowed_status, index=allowed_status.index(existing_status) if existing_status in allowed_status else 0)
        ai_note = st.text_input("Assistance IA utilisée et vérifications réalisées", original.get("ai_note", ""))
        if st.form_submit_button("Enregistrer la fiche", type="primary"):
            p = dict(id=original.get("id", ""), author=original.get("author", actor), name=name, ticker=ticker.strip().upper(),
                     sector=sector, thesis=thesis, fundamentals=fundamental, technical=technical, catalyst=catalyst,
                     risk=risk, invalidation=invalidation, sources=sources, target_weight=weight, bear=bear, base=base,
                     bull=bull, review_date=review.isoformat(), status=status, ai_note=ai_note)
            attempt(save_proposal, book, p, actor)

elif page == "Portefeuille":
    header("03 / ALLOCATION", "Les positions d’abord. Les cours ensuite.", "Les quantités et les liquidités viennent de votre relevé NextWise. Actualiser le marché ne les modifie jamais.")
    if st.button("Actualiser les cours", type="primary"):
        prices.clear()
        st.rerun()
    st.caption("Cours Yahoo indicatifs, cache de 15 minutes. Les dates restent visibles ; le prix d’exécution NextWise peut différer.")
    a, quotes = get_valuation()
    if not book["portfolio"]["initialized"]:
        st.warning("Portefeuille non initialisé : les 200 000 € ci-dessous sont uniquement la dotation théorique.")
    if a:
        cols = st.columns(4)
        cols[0].metric("Valeur indicative", f"{a['total']:,.0f} €".replace(",", " "))
        cols[1].metric("Liquidités", f"{book['portfolio']['cash']:,.0f} €".replace(",", " "))
        cols[2].metric("Plus grande exposition", f"{a['largest']:.1%}")
        cols[3].metric("Total des expositions > 5 %", f"{a['large_weight']:.1%}")
        for alert in a["alerts"]:
            st.warning(alert)
        if not a["alerts"]:
            st.success("Aucune alerte sur les contrôles indicatifs affichés. L’éligibilité et le classement restent ceux de NextWise.")
        if a["rows"]:
            display = pd.DataFrame(a["rows"])[["name", "ticker", "sector", "quantity", "price", "value", "weight", "date"]]
            display["weight"] *= 100
            st.dataframe(display.rename(columns={"name":"Valeur","ticker":"Code","sector":"Secteur","quantity":"Quantité","price":"Cours €","value":"Valeur €","weight":"Poids %","date":"Date du cours"}), hide_index=True, width="stretch")
            st.bar_chart(pd.Series({**{k:100*v for k,v in a['sectors'].items()}, "Liquidités":100*a['cash_weight']}, name="Poids (%)"), color="#55794a", horizontal=True)
    st.caption("Plafonds calculés sur titres + cash, regroupés par identifiant d’émetteur saisi. Les ETF ne sont pas décomposés : vérifier les chevauchements. Ces contrôles ne reproduisent pas le score officiel.")
    if can_edit:
        st.subheader("Reporter le portefeuille après exécution")
        st.write("Saisissez les quantités totales détenues et le cash restant. Un ordre en attente n’est pas encore une position.")
        with st.form("holdings"):
            frame = pd.DataFrame(book["portfolio"]["positions"], columns=["ticker", "name", "issuer", "quantity", "sector", "kind"])
            frame["quantity"] = frame["quantity"].astype("Int64")
            edited = st.data_editor(frame, num_rows="dynamic", hide_index=True, width="stretch", column_config={
                "ticker":st.column_config.TextColumn("Code Yahoo", required=True),
                "name":st.column_config.TextColumn("Nom"),
                "issuer":st.column_config.TextColumn("Émetteur / identifiant commun", help="Même identifiant pour deux lignes exposées au même émetteur. Pour un ETF, identifiant du fonds."),
                "quantity":st.column_config.NumberColumn("Quantité totale", min_value=0, step=1, required=True),
                "sector":st.column_config.SelectboxColumn("Secteur", options=[*SECTORS,"ETF diversifié","Autre","Non classé"], required=True),
                "kind":st.column_config.SelectboxColumn("Type", options=["Action","ETF"], required=True)})
            c1, c2 = st.columns(2)
            cash = c1.number_input("Liquidités restantes sur NextWise (€)", min_value=0.0, value=float(book["portfolio"]["cash"]), step=100.0)
            as_of = c2.date_input("Date du relevé", date.fromisoformat(book["portfolio"]["as_of"]) if book["portfolio"]["as_of"] else date.today(), max_value=date.today())
            note = st.text_input("Origine du relevé / raison de la modification")
            confirm = st.checkbox("J’ai vérifié ces quantités et le cash sur NextWise après exécution.")
            if st.form_submit_button("Enregistrer le portefeuille commun", type="primary"):
                if not confirm:
                    st.error("Vérifiez le relevé avant d’enregistrer.")
                else:
                    attempt(save_portfolio, book, edited.where(pd.notna(edited), None).to_dict("records"), cash, as_of.isoformat(), note, actor)
        with st.expander("Cours manquant : saisir un cours de secours"):
            st.caption("Utilisé uniquement si Yahoo ne fournit pas le cours. Il est daté et partagé, sans modifier les quantités ni le cash.")
            tickers = [p["ticker"] for p in book["portfolio"]["positions"]]
            if tickers:
                with st.form("manual_quote"):
                    symbol = st.selectbox("Valeur", tickers)
                    price = st.number_input("Cours en EUR", min_value=0.0001, value=1.0, format="%.4f")
                    qdate = st.date_input("Date du cours de secours", date.today(), max_value=date.today())
                    source = st.text_input("Source du cours")
                    if st.form_submit_button("Enregistrer ce cours daté"):
                        if not source.strip():
                            st.error("Indiquez la source.")
                        else:
                            candidate = deepcopy(book)
                            candidate["manual_quotes"][symbol] = {"price":price,"date":qdate.isoformat(),"currency":"EUR","source":source}
                            attempt(changed, candidate, actor, "Cours de secours enregistré : " + symbol)
    else:
        st.info("La coordination reporte les positions exécutées. Vous pouvez consulter et préparer vos analyses.")

elif page == "Comité":
    header("04 / DÉCISIONS", "Se retrouver tous les quatorze jours.", "Le compte rendu rassemble les raisons de vos choix. Un échange urgent reste possible entre deux comités.")
    st.markdown("**Ordre du jour :** faits nouveaux → risques cumulés → propositions → décision → responsable et prochaine vérification.")
    st.download_button("Télécharger l’ordre du jour et la synthèse", report(book), "comite-equipe.md", "text/markdown")
    ready = [p for p in book["proposals"] if p["status"] == "Prête pour le comité"]
    if ready:
        st.dataframe(pd.DataFrame([{"Proposition":p["name"],"Responsable":p["author"],"Secteur":p["sector"],"Poids envisagé %":p["target_weight"]} for p in ready]), hide_index=True, width="stretch")
        st.caption("Les poids proposés ne sont pas additionnés aux positions : ils doivent être arbitrés ensemble.")
    if can_edit:
        with st.form("decision"):
            st.subheader("Consigner une décision")
            action = st.selectbox("Décision", ["Ne rien changer", "Approfondir", "Proposer un achat sur NextWise", "Proposer une réduction sur NextWise", "Écarter la proposition"])
            proposal_ids = [""] + [p["id"] for p in book["proposals"]]
            labels = {p["id"]:p["name"] for p in book["proposals"]}
            pid = st.selectbox("Fiche liée", proposal_ids, format_func=lambda x:labels.get(x,"Décision globale"))
            reason = st.text_area("Raisonnement, désaccords, risque accepté et prochaine vérification")
            if st.form_submit_button("Enregistrer la décision", type="primary"):
                attempt(add_decision, book, actor, action, reason, pid)
        with st.form("meeting"):
            st.subheader("Compte rendu de réunion")
            a,b = st.columns(2)
            d = a.date_input("Date du comité", date.today(), max_value=date.today())
            next_d = b.date_input("Prochain comité (modifiable)", date.today()+timedelta(days=14), min_value=date.today())
            attendees = st.text_input("Participants présents")
            minutes = st.text_area("Constats et points discutés")
            next_actions = st.text_area("À faire : responsable, livrable et échéance")
            if st.form_submit_button("Enregistrer le compte rendu"):
                attempt(add_meeting, book, actor, d.isoformat(), attendees, minutes, next_actions, next_d.isoformat())
    st.subheader("Mémoire de l’équipe")
    for d in reversed(book["decisions"]):
        with st.expander(f"{d['at'][:10]} · {d['action']}"):
            st.write(d["reason"])
            st.caption(d["author"])
    for m in reversed(book["meetings"]):
        with st.expander(f"Comité du {m['date']}"):
            st.caption("Présents : " + m["participants"])
            st.write(m["minutes"])
            st.write(m["next_actions"])

elif page == "Équipe & cadre":
    header("05 / ORGANISATION", "Un cadre commun, des rôles clairs.", "Les responsables de secteur proposent ; la coordination vérifie la cohérence du portefeuille entier.")
    st.dataframe(pd.DataFrame([{"Secteur":s,"Responsable":n} for s,n in book["team"]["sectors"].items()]), hide_index=True, width="stretch")
    st.write(f"Coordination proposée : **{book['team']['coordinator']}** — allocation, suivi du code et préparation du comité.")
    st.caption("Ces rôles organisent votre travail ; ils n’inscrivent personne au club et ne donnent aucune autorisation sur NextWise.")
    st.subheader("Étape 1 · comprendre les limites")
    st.write("Le club compte 5 à 7 membres et démarre avec 200 000 € virtuels. Les limites 5/10/40 plafonnent une valeur à 10 % et le cumul des valeurs dépassant 5 % à 40 %. Le texte mentionne un repère de 16 titres.")
    st.info("Six secteurs ne signifient donc pas six actions. Le poids d’une position varie avec les cours : gardez de la marge et contrôlez l’ensemble après chaque décision.")
    st.write("Exemple purement arithmétique : 4 positions à 10 % et 12 à 5 % totalisent 100 % et respectent les seuils à cet instant. Cet exemple n’est pas une allocation recommandée ; il ne laisse aucune marge aux variations.")
    st.subheader("Ce que le concours regarde aussi")
    st.write("L’évaluation associe rendement, risque, diversification et participation : sources, outils NextWise, chats, travail collectif et quiz. Le travail dans cette application ne remplace pas vos contributions sur la plateforme.")
    st.subheader("Automatisation et IA")
    st.write("L’IA peut assister une analyse sourcée que vous savez expliquer. Les interactions artificielles et les bots sur la plateforme sont interdits. Cette application n’envoie aucun ordre, vote ou message à NextWise.")
    st.caption(f"Règlement consulté le {RULES_DATE}. Les indicateurs maison ne constituent pas le score officiel.")
    if can_edit:
        with st.expander("Modifier l’organisation"):
            with st.form("team"):
                team_name = st.text_input("Nom d’équipe", book["team"]["name"])
                coordinator = st.text_input("Coordination", book["team"]["coordinator"])
                assignments = {s:st.text_input(s, n) for s,n in book["team"]["sectors"].items()}
                if st.form_submit_button("Enregistrer les rôles"):
                    if not team_name.strip() or not coordinator.strip():
                        st.error("Renseignez le nom et la coordination.")
                    else:
                        candidate = deepcopy(book)
                        candidate["team"].update(name=team_name, coordinator=coordinator, sectors=assignments)
                        attempt(changed, candidate, actor, "Organisation mise à jour")

else:
    header("06 / ATELIER", "Un seul projet pour le code et le suivi.", "Au quotidien, tout se fait dans les écrans précédents. Cet espace sert aux sauvegardes et à la maintenance.")
    a,b = st.columns(2)
    with a, st.container(border=True):
        st.markdown("**Sauvegarde des données**")
        st.write("Partagée dans le dépôt privé, avec historique de versions." if shared else "Mode démonstration : la base partagée n’est pas encore raccordée.")
        st.download_button("Exporter une copie complète", encode(book), "nextchallenge-equipe.json", "application/json")
        st.caption("La copie contient les positions, analyses, décisions et réunions. Les cours Yahoo se recalculent séparément.")
    with b, st.container(border=True):
        st.markdown("**Automatisations disponibles**")
        st.write("• Cours à la consultation du portefeuille, cache 15 min.\n• Contrôles de concentration à chaque valorisation.\n• Fiches arrivées à leur date de revue.\n• Synthèse du comité à télécharger.\n• Tests à chaque changement du code sur GitHub.")
    st.subheader("Pour vous deux qui gérez la programmation")
    st.write("Créez une branche, modifiez le code, vérifiez les tests puis ouvrez une pull request. Votre amie peut relire les changements avant leur fusion.")
    if shared:
        st.link_button("Ouvrir le dépôt GitHub ↗", "https://github.com/" + config["storage"]["repository"])
    else:
        st.caption("Le README contient le démarrage local et les quelques réglages pour le mode partagé.")
    st.code("python -m unittest discover -s tests -v\nstreamlit run app.py", language="bash")
    st.caption("Aucun rappel externe ni tâche planifiée n’est actif. La date du comité est un repère dans l’application.")
    if can_edit:
        with st.expander("Restaurer une sauvegarde complète"):
            st.warning("La restauration remplace les données actuelles. Exportez-les d’abord. Elle ne fusionne pas deux versions.")
            upload = st.file_uploader("Sauvegarde JSON de cette application", type="json")
            checked = st.checkbox("J’ai sauvegardé la base actuelle et vérifié le fichier à restaurer.")
            if upload is not None:
                try:
                    imported = decode(upload.getvalue())
                    st.write(f"Aperçu : {len(imported['portfolio']['positions'])} positions, {len(imported['proposals'])} fiches, {len(imported['decisions'])} décisions.")
                    if st.button("Restaurer cette sauvegarde", disabled=not checked):
                        imported["revision"] = book["revision"]
                        imported["audit"] = deepcopy(book["audit"])
                        attempt(changed, imported, actor, "Restauration manuelle d’une sauvegarde complète")
                except ValueError as exc:
                    st.error(str(exc))
    with st.expander("Historique des enregistrements"):
        if book["audit"]:
            st.dataframe(pd.DataFrame(book["audit"][::-1]), hide_index=True, width="stretch")
        else:
            st.caption("Aucun enregistrement pour le moment.")
