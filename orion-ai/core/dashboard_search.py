"""Recherche locale dans les fiches du tableau de bord."""
from contextlib import closing
from urllib.parse import urlencode

from .wedding_notes import searchable


# Each query publishes a title and context only. The searchable text stays in SQLite.
SOURCES = {
    "project": ("""
        SELECT id,title,owner AS context,title||' '||owner||' '||note AS body FROM projects
    """, "projets", ("projet",)),
    "task": ("""
        SELECT t.project_id,t.id,t.title,p.title||' · '||t.owner AS context,
               t.title||' '||t.owner||' '||t.note||' '||p.title AS body
        FROM project_tasks t JOIN projects p ON p.id=t.project_id
    """, "projets", ("projet", "tache")),
    "ticket": ("""
        SELECT id,title,day AS context,id||' '||title AS body FROM business_items WHERE kind='tickets'
    """, "support", ("ticket",)),
    "document": ("""
        SELECT id,title,COALESCE(source_date,substr(created_at,1,10)) AS context,
               title||' '||source||' '||content AS body FROM inbox_entries
    """, "memoire", ("entree",)),
    "site": ("""
        SELECT id,name AS title,platform AS context,name||' '||url||' '||platform||' '||objective AS body
        FROM managed_sites
    """, "site", ("dossier",)),
    "wedding": ("""
        SELECT id,nom AS title,date AS context,nom AS body FROM wedding_plans
    """, "wedding", ("dossier",)),
}


def dashboard_search(query, kind, limit, connect_business, connect_wedding):
    terms = tuple(dict.fromkeys(searchable(query).split()))
    if not terms:
        raise ValueError("Saisissez au moins un terme de recherche.")
    phrase = " ".join(terms)
    results = []

    for name, (sql, page, parameters) in SOURCES.items():
        if kind != "all" and kind != name:
            continue
        connect = connect_wedding if name == "wedding" else connect_business
        filters = " AND ".join("instr(normalized(body), ?) > 0" for _ in terms)
        columns = "id, title, context, project_id" if name == "task" else "id, title, context"
        with closing(connect()) as db:
            db.create_function("normalized", 1, searchable, deterministic=True)
            rows = db.execute(f"""
                SELECT {columns}, CASE WHEN normalized(title)=? THEN 0
                    WHEN instr(normalized(title), ?)>0 THEN 1 ELSE 2 END AS rank
                FROM ({sql}) WHERE {filters} ORDER BY rank, normalized(title), id LIMIT ?
            """, (phrase, phrase, *terms, limit + 1))
            for row in rows:
                keys = ("project_id", "id") if name == "task" else ("id",)
                target = urlencode({parameter: row[key] for parameter, key in zip(parameters, keys, strict=True)})
                results.append({
                    "kind": name, "title": row["title"], "context": row["context"],
                    "href": "#" + page + "?" + target, "rank": row["rank"],
                })
    results.sort(key=lambda item: (item["rank"], searchable(item["title"]), item["href"]))
    return {"items": [{k: v for k, v in row.items() if k != "rank"} for row in results[:limit]],
            "has_more": len(results) > limit}
