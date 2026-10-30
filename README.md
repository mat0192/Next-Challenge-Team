# NextChallenge · Équipe

Un espace Streamlit pour préparer les analyses par secteur, décider ensemble et suivre le portefeuille du club. Projet distinct du dashboard solo.

## Où vous en êtes

Le projet est installé dans ce dépôt privé sous forme de fichiers utilisables. Vous n’avez plus besoin de téléverser ni de décompresser le ZIP.

**La prochaine étape est le déploiement Streamlit** : sélectionner le dépôt `mat0192/Next-Challenge-Team`, la branche `main` et le fichier `app.py`. Sans configuration des Secrets, le site s’ouvre en démonstration. La sauvegarde commune devient active après le raccordement décrit plus bas.

Les fichiers de cette page sont le code de l’application : ce ne sont pas des documents à remplir. Pour l’utilisation quotidienne, vous passerez par l’interface.

## Au quotidien (ou de façon hebdomadaire) : quatre gestes

1. **Analyses** : chacun prépare une fiche avec faits, sources, scénarios, risques et conditions d’invalidation.
2. **Comité** : tous les quatorze jours, discuter les propositions et consigner les décisions. Ne rien changer est une décision valable.
3. **Portefeuille** : après exécution d’un ordre sur NextWise, la coordination reporte les quantités totales et les liquidités du relevé.
4. Entre deux opérations, **Actualiser les cours**. Cela ne change jamais les quantités ou le cash.

L’organisation proposée reprend Tim, Sarah, Lucas, Diane, Layana et Jade, avec Mathis à la coordination. Les noms sont modifiables. Aucun membre n’a été invité, aucun actif acheté et aucune ancienne position solo copiée.

Le premier lancement est **une démonstration**, avec une dotation théorique et aucun relevé saisi. Le bandeau le signale. Les données de démonstration ne survivent pas à une nouvelle session : exporter avant de fermer. Le mode partagé décrit ci-dessous remplace cette démonstration.

## Essayer l’interface

Python 3.12 recommandé.

```sh
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py --server.address 127.0.0.1
```

Sur Windows, activer l’environnement avec `.venv\Scripts\activate`.

## Mise en service à deux — une seule fois

1. Le dépôt **privé** `Next-Challenge-Team` contient le code sur `main`.
2. La branche `team-data` contient la base initiale dans `data/team.json`. Elle conservera les données ; `main` conservera le code. Ne pas utiliser `team-data` pour déployer le code.
3. Déployer `main`, fichier `app.py`, sur Streamlit Community Cloud. Garder l’application **privée** et limiter son accès aux personnes de l’équipe. Partager le dépôt avec l’amie qui participe au code via les collaborateurs GitHub ; partager l’application avec les analystes n’exige pas de leur donner accès au code.
4. Dans GitHub, créer un jeton **fine-grained**, limité à ce seul dépôt privé, avec permission **Contents: Read and write**, et une expiration adaptée. Le jeton reste dans les **Secrets** de Streamlit ; ne pas le coller dans le code, un ticket ou une conversation.
5. Copier la structure de `secrets.example.toml` dans les Secrets de l’application. Renseigner le dépôt, le jeton et les comptes. Pour chaque compte, lancer localement `python manage.py hash-password` ; copier le hash obtenu dans les Secrets et transmettre sa phrase de passe à la personne par un canal privé. Chaque personne utilise un compte distinct. La coordination a le rôle `editor`, les analystes `analyst`.
6. Ouvrir l’application et se connecter. Le bandeau démonstration doit avoir disparu. Enregistrer un premier relevé ou une fiche, puis vérifier depuis un second compte après **Recharger les données d’équipe**.

Sans cette configuration, l’application reste explicitement en démonstration. La présence du dépôt GitHub ne signifie pas que le site est déjà en ligne. Aucun jeton, compte réel ou accès à des tiers n’est créé par le code.

## Sauvegarde et travail simultané

Le fichier partagé appartient au dépôt privé, pas à un navigateur. Fermer ou redémarrer Streamlit ne l’efface pas. Chaque écriture utilise la version GitHub du fichier lu : si quelqu’un enregistre avant vous, l’écriture est refusée, un brouillon est téléchargeable et vous pouvez recharger puis reprendre votre modification. Il n’existe pas de fusion automatique risquant de perdre un changement.

La branche `team-data` sépare les enregistrements du code déployé : une fiche enregistrée ne redéploie pas `main`. Recharger avant de saisir ; la lecture des modifications d’un collègue n’est pas instantanée. Si GitHub est indisponible ou le fichier illisible, aucune base vide n’est substituée silencieusement.

**Code & automatisation** permet d’exporter le JSON complet, consulter le journal et restaurer une sauvegarde après vérification. Les commits de `team-data` conservent les versions précédentes. Le JSON solo n’est pas compatible : le club démarre avec sa propre base. Taille maximale : 900 Ko, adaptée à un petit club ; archiver les anciens journaux si nécessaire. Ne jamais passer ce dépôt en public : les versions historiques contiennent aussi les analyses.

## Les automatisations déjà dans le projet

- Chargement des cours quand le portefeuille est consulté, avec cache de quinze minutes et bouton d’actualisation.
- Contrôles des plafonds, cours manquants, dates anciennes, quantités et cash.
- Mise en avant des fiches dont la date de revue est arrivée.
- Synthèse du comité générée depuis la base, téléchargeable dans l’application.
- Tests GitHub Actions sur chaque changement de `main` ou pull request ; lancement manuel possible dans **Actions**.

Aucune tâche périodique, notification externe ou interaction NextWise n’est activée. Le calendrier est un repère interne. La synthèse peut aussi être produite localement avec `python manage.py report --file chemin/sauvegarde.json`.

## Interprétation des indicateurs

Le cadre du club, les limites et le lien du [règlement officiel](https://www.nextwise.fr/le-reglement) consulté le **29 octobre 2026** sont dans **Équipe & cadre**. Le portefeuille vide n’est pas déclaré conforme : il reste à construire. Les six responsabilités de recherche ne fixent ni le nombre de titres ni leurs poids.

La valorisation utilise la dernière clôture quotidienne brute Yahoo disponible, exclusivement en EUR. Aucun taux de change implicite. Une donnée manquante empêche l’affichage d’un total incomplet. En secours, la coordination peut saisir un cours EUR sourcé et daté ; il est utilisé seulement si Yahoo est indisponible. Un cours de plus de sept jours déclenche une alerte. La date du relevé de positions est indépendante de celle des cours.

Les expositions sont calculées sur titres + liquidités et regroupées par l’identifiant d’émetteur saisi. Le seuil de 5 % est strict : exactement 5 % n’entre pas dans le cumul. L’exemple arithmétique du cadre n’est pas une recommandation. Aucun plafond sectoriel supplémentaire n’est inventé. Les ETF ne sont pas décomposés : leurs chevauchements et leur éligibilité se vérifient sur NextWise. Ni score officiel, ni performance ajustée des flux, ni avantage prédictif ne sont revendiqués. Les scénarios sont des hypothèses explicites de l’auteur.

## Code : où intervenir

| Fichier | Rôle |
|---|---|
| `app.py` | Les six écrans de l’interface |
| `core.py` | Validation, allocations, analyses et journaux |
| `storage.py` | Base GitHub, conflits et vérification des phrases de passe |
| `market.py` | Lecture des cours, sans écriture du portefeuille |
| `tests/` | Vérifications des calculs, sauvegardes et parcours |

Pour travailler à deux : créer une branche de code, proposer une pull request, attendre les tests et faire relire avant fusion dans `main`. Ne pas modifier `data/team.json` à la main pendant qu’une personne saisit dans l’application.

```sh
python -m unittest discover -s tests -v
```

Références techniques : [API Contents GitHub](https://docs.github.com/en/rest/repos/contents), [Streamlit Secrets](https://docs.streamlit.io/develop/concepts/connections/secrets-management), [yfinance](https://ranaroussi.github.io/yfinance/reference/api/yfinance.Ticker.history.html).
