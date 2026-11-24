"""Vue transversale des propositions en attente de validation."""
from contextlib import closing
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from urllib.parse import urlencode


def pending_approvals(today, wedding, sites, templates, stage="pending"):
    items = []
    for plan in wedding.checklist.list():
        data = wedding.read(plan["id"])
        records = data["records"]
        if records["client"].get("client", {}).get("stage") == "closed":
            continue
        current = dict(wedding.candidates(records, today, 90))
        for reminder in data["reminders"]:
            identity = (reminder["kind"], reminder["target"], reminder["due"])
            item = current.get(identity)
            state = reminder["status"]
            expected = {"draft"} if stage == "pending" else {"approved", "sending", "sent", "unknown"}
            if state not in expected:
                continue
            if state in ("draft", "approved") and (
                item is None or any(item[field] != reminder[field] for field in ("email", "message"))
            ):
                continue
            items.append({
                "source": "wedding", "state": state, "dossier": plan["nom"], "title": reminder["subject"],
                "date": reminder["due"], "urgent": reminder["due"] <= today.isoformat(),
                "href": "#wedding?" + urlencode({"dossier": plan["id"], "relance": ":".join(identity)}),
            })

    names = {entry["id"]: entry["title"] for entry in templates}
    with closing(sites.connect()) as db:
        for row in db.execute("""
            SELECT i.id,i.site_id,i.template,i.state,COALESCE(i.approved_at,i.created_at) AS relevant_at,s.name
            FROM site_interventions i JOIN managed_sites s ON s.id=i.site_id
            WHERE i.state=?
        """, ("draft" if stage == "pending" else "approved",)):
            items.append({
                "source": "site", "state": row["state"], "dossier": row["name"],
                "title": names.get(row["template"], row["template"]),
                "date": row["relevant_at"][:10], "urgent": False,
                "href": "#site?" + urlencode({"dossier": row["site_id"], "intervention": row["id"]}),
            })
    items.sort(key=lambda row: (not row["urgent"], row["date"], row["dossier"].casefold(), row["href"]))
    return {"date": today.isoformat(), "count": len(items), "items": items}



def decision_history(today, wedding, sites, templates):
    items = []
    paris = ZoneInfo("Europe/Paris")

    def add(category, dossier, title, href, state, when):
        date = when
        if when and len(when) > 10:
            stamp = datetime.fromisoformat(when)
            date = (stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)).astimezone(paris).date().isoformat()
        items.append({"source": category, "dossier": dossier, "title": title, "href": href,
                      "state": state, "date": date, "urgent": False})

    for plan in wedding.checklist.list():
        for row in wedding.read(plan["id"])["reminders"]:
            identity = ":".join((row["kind"], row["target"], row["due"]))
            href = "#wedding?" + urlencode({"dossier": plan["id"], "relance": identity})
            def add_reminder(state, when):
                add("wedding", plan["nom"], row["subject"], href, state, when)
            if row.get("approved_at"):
                add_reminder("approved", row["approved_at"])
            if row.get("mail_outcome") in ("accepted", "unknown"):
                add_reminder("sent" if row["mail_outcome"] == "accepted" else "unknown",
                             row.get("mail_finished_at"))
            if row["status"] == "dismissed":
                add_reminder("dismissed", row.get("dismissed_at"))
            if row["status"] == "recorded":
                add_reminder("recorded", row.get("recorded_at"))

    names = {entry["id"]: entry["title"] for entry in templates}
    with closing(sites.connect()) as db:
        for row in db.execute("""
            SELECT i.id,i.site_id,i.template,i.state,i.approved_at,i.verified_at,s.name,r.rejected_at
            FROM site_interventions i JOIN managed_sites s ON s.id=i.site_id
            LEFT JOIN site_intervention_rejections r ON r.intervention_id=i.id
            WHERE i.state IN ('approved','verified','rejected')
        """):
            href = "#site?" + urlencode({"dossier": row["site_id"], "intervention": row["id"]})
            title = names.get(row["template"], row["template"])
            if row["approved_at"]:
                add("site", row["name"], title, href, "approved", row["approved_at"])
            if row["state"] == "verified":
                add("site", row["name"], title, href, "verified", row["verified_at"])
            if row["state"] == "rejected":
                add("site", row["name"], title, href, "rejected", row["rejected_at"])

    items.reverse()
    items.sort(key=lambda item: item["date"] or "", reverse=True)
    return {"date": today.isoformat(), "count": len(items), "items": items}
