"""Shared GitHub JSON with optimistic locking; never silently reset data."""
import base64
import hashlib
import hmac
import json
import re
import secrets
import requests
from core import fresh, validate


class ConflictError(RuntimeError):
    pass


class StorageError(RuntimeError):
    pass


def encode(state):
    validate(state)
    return json.dumps(state, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")


def decode(raw):
    if len(raw) > 900000:
        raise ValueError("Sauvegarde trop volumineuse (maximum 900 Ko).")
    try:
        return validate(json.loads(raw))
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError("Sauvegarde illisible ou invalide. La base actuelle est conservée.") from exc


class GitHubStore:
    def __init__(self, repo, token, branch="team-data", path="data/team.json", session=None):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
            raise StorageError("Nom de dépôt invalide.")
        if path != "data/team.json":
            raise StorageError("Le fichier de données doit être data/team.json.")
        self.root = "https://api.github.com/repos/" + repo
        self.url = self.root + "/contents/" + path
        self.branch = branch
        self.session = session or requests.Session()
        self.session.headers.update({"Authorization": "Bearer " + token,
                                     "Accept": "application/vnd.github+json",
                                     "X-GitHub-Api-Version": "2022-11-28"})

    def _request(self, method, url, **kwargs):
        try:
            return self.session.request(method, url, timeout=20, **kwargs)
        except requests.RequestException:
            raise StorageError("GitHub ne répond pas. Aucune sauvegarde n’est confirmée ; réessayez après rechargement.") from None

    def load(self):
        meta = self._request("GET", self.root)
        if meta.status_code != 200:
            raise StorageError("Accès au dépôt impossible. Vérifiez le dépôt et les secrets de l’application.")
        if not meta.json().get("private"):
            raise StorageError("Le mode partagé exige un dépôt privé pour protéger les analyses de l’équipe.")
        response = self._request("GET", self.url, params={"ref": self.branch})
        if response.status_code == 404:
            # A missing branch is a configuration error, not a new empty book.
            branch = self._request("GET", self.root + "/branches/" + self.branch)
            if branch.status_code != 200:
                raise StorageError("La branche de données n’existe pas.")
            return fresh(), None
        if response.status_code != 200:
            raise StorageError(f"Lecture impossible (GitHub {response.status_code}). Aucune réinitialisation.")
        body = response.json()
        try:
            return decode(base64.b64decode(body["content"])), body["sha"]
        except (ValueError, KeyError, TypeError):
            raise StorageError("Le fichier partagé est invalide. Il n’a pas été écrasé.") from None

    def save(self, state, expected_sha):
        raw = encode(state)
        if len(raw) > 900000:
            raise StorageError("Limite de 900 Ko atteinte : exportez et archivez avant de continuer.")
        payload = {"message": f"Équipe : sauvegarde r{state['revision']}",
                   "content": base64.b64encode(raw).decode(), "branch": self.branch}
        if expected_sha:
            payload["sha"] = expected_sha
        response = self._request("PUT", self.url, json=payload)
        if response.status_code in (409, 422):
            raise ConflictError("Une autre sauvegarde a été faite entre-temps. Votre saisie n’a pas été envoyée. "
                                "Copiez-la, puis rechargez les données de l’équipe avant de réessayer.")
        if response.status_code not in (200, 201):
            raise StorageError(f"Sauvegarde refusée (GitHub {response.status_code}). Vos changements ne sont pas enregistrés.")
        return response.json()["content"]["sha"]


def hash_password(password, salt=None):
    if len(password) < 16:
        raise ValueError("Utilisez une phrase de passe d’au moins 16 caractères.")
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600000).hex()
    return f"pbkdf2_sha256$600000${salt}${digest}"


def verify_password(password, encoded):
    try:
        algorithm, rounds, salt, digest = encoded.split("$")
        if algorithm != "pbkdf2_sha256" or not 100000 <= int(rounds) <= 1000000:
            return False
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(rounds)).hex()
        return hmac.compare_digest(candidate, digest)
    except (ValueError, TypeError, AttributeError):
        return False
