"""Small local maintenance commands; passwords never enter source control."""
import argparse
import getpass
from pathlib import Path
from core import fresh, report
from storage import encode, decode, hash_password

parser = argparse.ArgumentParser(description="Maintenance NextChallenge équipe")
parser.add_argument("command", choices=["hash-password", "init-data", "report"])
parser.add_argument("--file", default="data/team.json")
args = parser.parse_args()
if args.command == "hash-password":
    password = getpass.getpass("Phrase de passe (16 caractères minimum) : ")
    confirm = getpass.getpass("Confirmer : ")
    if password != confirm:
        parser.error("Les phrases de passe ne correspondent pas.")
    print(hash_password(password))
elif args.command == "init-data":
    destination = Path(args.file)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Refuse overwrites, even when an operator runs the command twice.
    with destination.open("xb") as stream:
        stream.write(encode(fresh()))
    print("Base vide créée :", destination)
else:
    print(report(decode(Path(args.file).read_bytes())))
