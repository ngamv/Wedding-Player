"""Agenda en lecture seule à partir des échéances ORION."""
from contextlib import closing
from datetime import timedelta


def build_agenda(start, days, kind, business, wedding):
    try:
        end = start + timedelta(days=days - 1)
    except OverflowError as error:
        raise ValueError("La période dépasse la plage des dates.") from error
    bounds = (start.isoformat(), end.isoformat())
    items = []

    def add(category, row, title, when, link, context=""):
        items.append({"id": row["id"], "kind": category, "date": when,
                      "title": title, "detail": context, "link": link})

    with closing(business.connect()) as db:
        db.execute("BEGIN")
        if kind in ("all", "appointment"):
            for row in db.execute("""
                SELECT id,title,day FROM business_items
                WHERE kind='appointments' AND status='scheduled' AND day BETWEEN ? AND ?
            """, bounds):
                add("appointment", row, row["title"], row["day"], "#ceo?imports=1", "Rendez-vous importé")
        if kind in ("all", "project"):
            for row in db.execute("""
                SELECT id,title,owner,due FROM projects WHERE status<>'done' AND due BETWEEN ? AND ?
            """, bounds):
                add("project", row, row["title"], row["due"], "#projets?projet=" + row["id"], row["owner"])
        if kind in ("all", "task"):
            for row in db.execute("""
                SELECT t.id,t.title,t.owner,t.due,t.project_id,p.title AS project_title
                FROM project_tasks t JOIN projects p ON p.id=t.project_id
                WHERE t.status<>'done' AND p.status<>'done' AND t.due BETWEEN ? AND ?
            """, bounds):
                add("task", row, row["title"], row["due"],
                    "#projets?projet=" + row["project_id"] + "&tache=" + row["id"],
                    row["project_title"] + " · " + row["owner"])
    if kind in ("all", "wedding"):
        with closing(wedding.checklist.connect()) as db:
            for row in db.execute("""
                SELECT p.id,p.nom,p.date FROM wedding_plans p
                LEFT JOIN wedding_records r ON r.plan=p.id AND r.kind='client' AND r.id='client'
                WHERE p.date BETWEEN ? AND ? AND COALESCE(json_extract(r.data,'$.stage'),'')<>'closed'
            """, bounds):
                add("wedding", row, row["nom"], row["date"], "#wedding?dossier=" + row["id"])
    items.sort(key=lambda item: (item["date"], item["kind"], item["title"].casefold(), item["id"]))
    return {"start": bounds[0], "end": bounds[1], "count": len(items), "items": items[:500]}
