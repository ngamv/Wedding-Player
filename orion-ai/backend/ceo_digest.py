"""Génère et enregistre le brief du CEO sans lancer le serveur web."""
import json

from backend.main import ceo_jobs, generate_ceo_brief, wedding_today


if __name__ == "__main__":
    jobs = ceo_jobs()
    job = jobs.enqueue(wedding_today(), "scheduler")
    report = jobs.run(job["id"], generate_ceo_brief)
    if report is None:
        print(json.dumps({"job": job["id"], "detail": "Brief en cours ou génération interrompue."}))
        raise SystemExit(1)
    sync_errors = [name for name, state in report["file_sync"].items() if state["state"] == "error"]
    print(json.dumps({"date": report["date"], "count": report["count"], "sources": report["sources"],
                      "sync_errors": sync_errors}))
    raise SystemExit(int(bool(sync_errors) or "error" in report["sources"].values()))
