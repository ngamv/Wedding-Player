import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def wedding_templates():
    return json.loads((ROOT / "config" / "wedding.json").read_text(encoding="utf-8"))


def wedding_plan(template_id, brief=""):
    if len(brief) > 7000:
        raise ValueError("Le brief est limité à 7 000 caractères.")
    for template in wedding_templates():
        if template["id"] == template_id:
            task = template["task"]
            if brief.strip():
                task += "\n\nBrief transmis :\n" + brief.strip()
            return {
                "task": task + "\nLivrables pour validation humaine. Toute action externe doit être validée.",
                "agent_ids": template["agent_ids"],
            }
    raise ValueError("Modèle de mariage inconnu.")
