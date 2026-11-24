"""Registre local des sites et journal des interventions."""
import json
import sqlite3
from contextlib import closing
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def site_templates():
    return json.loads((ROOT / "config/site_workflows.json").read_text(encoding="utf-8"))


class NoGitHubRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def github_metadata(repo):
    owner, name = repo.split("/")
    request = Request(f"https://api.github.com/repos/{owner}/{name}", headers={
        "User-Agent": "ORION-Site", "Accept": "application/vnd.github+json",
    })
    try:
        with build_opener(NoGitHubRedirect()).open(request, timeout=8) as response:
            payload = response.read(262145)
        if len(payload) > 262144:
            raise ValueError("Réponse GitHub trop volumineuse.")
        data = json.loads(payload)
        if not isinstance(data, dict) or data.get("private") is not False:
            raise ValueError("Le dépôt doit être public.")
        return {key: data[key] for key in ("full_name", "default_branch", "pushed_at", "archived")}
    except HTTPError as error:
        raise ValueError(f"GitHub HTTP {error.code}. Vérifiez le dépôt public et les quotas.") from error
    except (URLError, HTTPException, OSError, KeyError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("GitHub est indisponible ou a renvoyé une réponse inattendue.") from error


class SiteOperations:
    def __init__(self, path):
        self.path = path
        with closing(self.connect()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS managed_sites (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL,
                    platform TEXT NOT NULL, repo TEXT NOT NULL, objective TEXT NOT NULL,
                    github TEXT, synced_at TEXT
                );
                CREATE TABLE IF NOT EXISTS site_interventions (
                    id TEXT PRIMARY KEY, site_id TEXT NOT NULL, template TEXT NOT NULL,
                    workflow_id TEXT NOT NULL, state TEXT NOT NULL,
                    result TEXT NOT NULL DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    approved_at TEXT, verified_at TEXT
                );
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def site(row):
        if row is None:
            raise KeyError("Site introuvable.")
        return {**dict(row), "github": json.loads(row["github"]) if row["github"] else None}

    def list(self):
        with closing(self.connect()) as db:
            return [self.site(row) for row in db.execute("SELECT * FROM managed_sites ORDER BY name, id")]

    def get(self, site_id):
        with closing(self.connect()) as db:
            return self.site(db.execute("SELECT * FROM managed_sites WHERE id=?", (site_id,)).fetchone())

    def save(self, data, site_id=None):
        fields = ("name", "url", "platform", "repo", "objective")
        values = tuple(data[key].strip() for key in fields)
        with closing(self.connect()) as db, db:
            if site_id is None:
                site_id = uuid4().hex
                db.execute("INSERT INTO managed_sites VALUES (?, ?, ?, ?, ?, ?, NULL, NULL)",
                           (site_id, *values))
            else:
                changed = db.execute("""
                    UPDATE managed_sites SET name=?, url=?, platform=?,
                        github=CASE WHEN repo=? THEN github END,
                        synced_at=CASE WHEN repo=? THEN synced_at END,
                        repo=?, objective=? WHERE id=?
                """, (*values[:3], values[3], values[3], *values[3:], site_id))
                if not changed.rowcount:
                    raise KeyError("Site introuvable.")
        return self.get(site_id)

    def sync(self, site_id):
        site = self.get(site_id)
        if not site["repo"]:
            raise ValueError("Renseignez un dépôt GitHub public.")
        metadata = github_metadata(site["repo"])
        with closing(self.connect()) as db, db:
            changed = db.execute("""
                UPDATE managed_sites SET github=?, synced_at=CURRENT_TIMESTAMP WHERE id=? AND repo=?
            """, (json.dumps(metadata), site_id, site["repo"]))
            if not changed.rowcount:
                raise ValueError("Le dépôt a changé pendant la synchronisation.")
        return self.get(site_id)

    def log(self, site_id, template, run):
        intervention = uuid4().hex
        state = {"completed": "draft", "failed": "failed"}[run["status"]]
        if state == "draft" and not any(step["result"] and step["mode"] != "simulation" for step in run["steps"]):
            state = "simulation"
        with closing(self.connect()) as db, db:
            db.execute("""
                INSERT INTO site_interventions (id, site_id, template, workflow_id, state) VALUES (?, ?, ?, ?, ?)
            """, (intervention, site_id, template, run["id"], state))
        return self.intervention(site_id, intervention)

    def history(self, site_id):
        self.get(site_id)
        with closing(self.connect()) as db:
            return [dict(row) for row in db.execute("""
                SELECT * FROM site_interventions WHERE site_id=? ORDER BY rowid DESC LIMIT 30
            """, (site_id,))]

    def brief_queue(self):
        with closing(self.connect()) as db:
            return [dict(row) for row in db.execute("""
                WITH current AS (
                    SELECT i.*, ROW_NUMBER() OVER(PARTITION BY site_id, template ORDER BY rowid DESC) AS ranking
                    FROM site_interventions i WHERE state<>'simulation'
                )
                SELECT c.site_id, c.template, c.state, s.name FROM current c
                JOIN managed_sites s ON s.id=c.site_id
                WHERE (c.state='failed' AND c.ranking=1) OR c.state IN ('draft','approved')
            """)]

    def intervention(self, site_id, intervention):
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM site_interventions WHERE site_id=? AND id=?",
                             (site_id, intervention)).fetchone()
        if row is None:
            raise KeyError("Intervention introuvable sur ce site.")
        return dict(row)

    def advance(self, site_id, intervention, action, result):
        self.intervention(site_id, intervention)
        with closing(self.connect()) as db, db:
            if action == "approve":
                changed = db.execute("""
                    UPDATE site_interventions SET state='approved', approved_at=CURRENT_TIMESTAMP
                    WHERE site_id=? AND id=? AND state='draft'
                """, (site_id, intervention))
            else:
                changed = db.execute("""
                    UPDATE site_interventions SET state='verified', result=?, verified_at=CURRENT_TIMESTAMP
                    WHERE site_id=? AND id=? AND state='approved'
                """, (result, site_id, intervention))
            if not changed.rowcount:
                raise ValueError("Cette action est incompatible avec l’état de l’intervention.")
        return self.intervention(site_id, intervention)
