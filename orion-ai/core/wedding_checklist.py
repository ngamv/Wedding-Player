"""Rétroplanning local et état persistant des mariages."""

import json
import sqlite3
from contextlib import closing
from datetime import date, timedelta
from uuid import uuid4

from .wedding import ROOT

OPTIONS = {
    "religieuse": "Cérémonie religieuse",
    "laique": "Cérémonie laïque",
    "contrat": "Contrat de mariage",
    "lune_de_miel": "Lune de miel",
    "audition": "Audition demandée par la mairie",
}


def generer(event_date, options=()):
    unknown = set(options) - OPTIONS.keys()
    if unknown:
        raise ValueError("Option inconnue : " + ", ".join(sorted(unknown)))
    templates = json.loads((ROOT / "config/wedding_checklist.json").read_text(encoding="utf-8"))
    tasks = [t for t in templates if not t.get("option") or t["option"] in options]
    active = {t["id"] for t in tasks}
    try:
        return [
            {**t, "echeance": (event_date + timedelta(days=t["offset"])).isoformat(),
             "dependances": [d for d in t["dependances"] if d in active], "terminee": False}
            for t in tasks
        ]
    except OverflowError as error:
        raise ValueError("Date hors plage du rétroplanning.") from error


class WeddingChecklist:
    def __init__(self, path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS wedding_plans (
                id TEXT PRIMARY KEY, nom TEXT NOT NULL, date TEXT NOT NULL,
                options TEXT NOT NULL, tasks TEXT NOT NULL
            )""")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def decode(row):
        return {**dict(row), "options": json.loads(row["options"]), "tasks": json.loads(row["tasks"])}

    def create(self, nom, event_date, options):
        nom = nom.strip()
        if not 1 <= len(nom) <= 120:
            raise ValueError("Indiquez un nom de projet de 1 à 120 caractères.")
        options = sorted(set(options))
        plan = {"id": uuid4().hex, "nom": nom, "date": event_date.isoformat(),
                "options": options, "tasks": generer(event_date, options)}
        with closing(self.connect()) as db, db:
            db.execute("INSERT INTO wedding_plans VALUES (?, ?, ?, ?, ?)", (
                plan["id"], nom, plan["date"], json.dumps(options), json.dumps(plan["tasks"], ensure_ascii=False)
            ))
        return plan

    def list(self):
        with closing(self.connect()) as db:
            return [dict(row) for row in db.execute("SELECT id, nom, date FROM wedding_plans ORDER BY date, nom, id")]

    def get(self, plan_id):
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM wedding_plans WHERE id=?", (plan_id,)).fetchone()
        if row is None:
            raise KeyError("Mariage inconnu.")
        return self.decode(row)

    def reschedule(self, plan_id, event_date):
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM wedding_plans WHERE id=?", (plan_id,)).fetchone()
            if row is None:
                raise KeyError("Mariage inconnu.")
            plan = self.decode(row)
            try:
                for task in plan["tasks"]:
                    task["echeance"] = (event_date + timedelta(days=task["offset"])).isoformat()
            except OverflowError as error:
                raise ValueError("Date hors plage du rétroplanning.") from error
            plan["date"] = event_date.isoformat()
            db.execute("UPDATE wedding_plans SET date=?, tasks=? WHERE id=?", (
                plan["date"], json.dumps(plan["tasks"], ensure_ascii=False), plan_id
            ))
        return plan

    def complete(self, plan_id, task_id, done):
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM wedding_plans WHERE id=?", (plan_id,)).fetchone()
            if row is None:
                raise KeyError("Mariage inconnu.")
            plan = self.decode(row)
            tasks = {t["id"]: t for t in plan["tasks"]}
            if task_id not in tasks:
                raise KeyError("Tâche absente de ce mariage.")
            task = tasks[task_id]
            if done and any(not tasks[d]["terminee"] for d in task["dependances"]):
                raise ValueError("Terminez les prérequis avant cette tâche.")
            if not done and any(t["terminee"] and task_id in t["dependances"] for t in tasks.values()):
                raise ValueError("Rouvrez d’abord les tâches terminées qui en dépendent.")
            task["terminee"] = done
            db.execute("UPDATE wedding_plans SET tasks=? WHERE id=?", (
                json.dumps(plan["tasks"], ensure_ascii=False), plan_id
            ))
        return plan

    def digest(self, plan_id, today, days=7):
        if not 0 <= days <= 90:
            raise ValueError("Fenêtre de 0 à 90 jours.")
        plan = self.get(plan_id)
        try:
            until = (today + timedelta(days=days)).isoformat()
        except OverflowError as error:
            raise ValueError("Date de synthèse hors plage.") from error
        done = {t["id"] for t in plan["tasks"] if t["terminee"]}
        pending = [
            {**t, "bloquee": not set(t["dependances"]) <= done}
            for t in plan["tasks"] if not t["terminee"] and t["echeance"] <= until
        ]
        return {"id": plan_id, "date": today.isoformat(), "jusqu_au": until,
                "en_retard": [t for t in pending if t["echeance"] < today.isoformat()],
                "a_venir": [t for t in pending if t["echeance"] >= today.isoformat()]}

    def digest_all(self, today, days=7):
        return [
            {**self.digest(plan["id"], today, days), "nom": plan["nom"], "mariage": plan["date"]}
            for plan in self.list()
        ]
