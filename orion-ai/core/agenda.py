"""Agenda en lecture seule à partir des échéances ORION."""
from contextlib import closing
from hashlib import sha256
from uuid import uuid4
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta, timezone


def build_agenda(start, days, kind, business, wedding, limit=500, include_cancelled=False):
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
                SELECT b.id,b.title,b.day,b.status,l.clock,l.duration,l.utc_start,l.utc_end,l.note,
                       a.target_kind,a.target_id,
                       (b.status='scheduled' AND EXISTS (
                           SELECT 1 FROM local_appointments other
                           JOIN business_items o ON o.kind='appointments' AND o.id=other.id
                           WHERE o.status='scheduled' AND other.id<>l.id
                             AND other.utc_start<l.utc_end AND other.utc_end>l.utc_start
                       )) AS overlap
                FROM business_items b LEFT JOIN local_appointments l ON l.id=b.id
                LEFT JOIN appointment_links a ON a.appointment_id=l.id
                WHERE b.kind='appointments' AND b.day BETWEEN ? AND ?
                AND (b.status='scheduled' OR (? AND b.status='cancelled' AND l.id IS NOT NULL))
            """, (*bounds, include_cancelled)):
                local = row["clock"] is not None
                add("appointment", row, row["title"], row["day"], None if local else "#ceo?imports=1",
                    row["note"] if local else "Rendez-vous importé")
                if local:
                    items[-1].update(clock=row["clock"], duration=row["duration"], status=row["status"],
                                     utc_start=row["utc_start"], utc_end=row["utc_end"],
                                     target_kind=row["target_kind"], target_id=row["target_id"],
                                     overlap=bool(row["overlap"]))
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
    items.sort(key=lambda item: (item["date"], item.get("clock", ""), item["kind"], item["title"].casefold(), item["id"]))
    return {"start": bounds[0], "end": bounds[1], "count": len(items), "items": items[:limit]}



def calendar_text(value):
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = "".join(char for char in value if ord(char) >= 32 or char == "\n")
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")


def fold_calendar_line(line):
    parts = []
    current = bytearray()
    for char in line:
        encoded = char.encode("utf-8")
        if len(current) + len(encoded) > 75:
            parts.append(bytes(current))
            current = bytearray(b" ")
        current.extend(encoded)
    parts.append(bytes(current))
    return b"\r\n".join(parts)


def export_calendar(items, generated_at=None):
    now = generated_at or datetime.now(timezone.utc)
    stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    labels = {"appointment": "Rendez-vous", "wedding": "Mariage", "project": "Projet", "task": "Tâche"}
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//ORION//Agenda//FR", "CALSCALE:GREGORIAN"]
    for item in items:
        identity = f'{item["kind"]}:{item["id"]}'
        uid = sha256(identity.encode("utf-8")).hexdigest()
        category = labels[item["kind"]]
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}@agenda.orion.local",
            f"DTSTAMP:{stamp}",
            *(
                ["DTSTART:" + datetime.fromisoformat(item["utc_start"]).strftime("%Y%m%dT%H%M%SZ"),
                 "DTEND:" + datetime.fromisoformat(item["utc_end"]).strftime("%Y%m%dT%H%M%SZ")]
                if item.get("utc_start") else ["DTSTART;VALUE=DATE:" + item["date"].replace("-", "")]
            ),
            "SUMMARY:" + calendar_text(item["title"]),
            "CATEGORIES:" + calendar_text(category),
        ])
        if item["detail"]:
            lines.append("DESCRIPTION:" + calendar_text(item["detail"]))
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return b"\r\n".join(fold_calendar_line(line) for line in lines) + b"\r\n"



def save_appointment(business, data, key=None):
    local = datetime.combine(data["day"], datetime.strptime(data["clock"], "%H:%M").time())
    paris = ZoneInfo("Europe/Paris")
    try:
        slots = {
            local.replace(tzinfo=paris, fold=fold).astimezone(timezone.utc) for fold in (0, 1)
        }
        valid = [slot for slot in slots if slot.astimezone(paris).replace(tzinfo=None) == local]
        if len(valid) != 1:
            raise ValueError("Cette heure est ambiguë ou inexistante à Paris. Choisissez un autre créneau.")
        start = valid[0]
        end = start + timedelta(minutes=data["duration"])
    except OverflowError as error:
        raise ValueError("L’horaire dépasse la plage des dates.") from error

    with closing(business.connect()) as db, db:
        values = (data["title"].strip(), data["day"].isoformat(), data["status"])
        detail = (data["clock"], data["duration"], start.isoformat(), end.isoformat(), data["note"].strip())
        if key is None:
            key = "orion-" + uuid4().hex
            db.execute("INSERT INTO business_items VALUES ('appointments', ?, ?, ?, ?, 0)", (key, *values))
            db.execute("INSERT INTO local_appointments VALUES (?,?,?,?,?,?)", (key, *detail))
        else:
            changed = db.execute("""
                UPDATE local_appointments SET clock=?, duration=?, utc_start=?, utc_end=?, note=? WHERE id=?
            """, (*detail, key))
            if not changed.rowcount:
                raise KeyError("Rendez-vous local introuvable.")
            db.execute("UPDATE business_items SET title=?, day=?, status=? WHERE kind='appointments' AND id=?",
                       (*values, key))
        if data.get("target_kind"):
            db.execute("""
                INSERT INTO appointment_links VALUES (?,?,?)
                ON CONFLICT(appointment_id) DO UPDATE SET target_kind=excluded.target_kind,target_id=excluded.target_id
            """, (key, data["target_kind"], data["target_id"]))
        else:
            db.execute("DELETE FROM appointment_links WHERE appointment_id=?", (key,))
    return {"id": key}
