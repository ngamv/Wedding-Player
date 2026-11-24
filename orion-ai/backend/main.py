import json
import logging
import os
import re
from functools import lru_cache
from typing import Literal
from zoneinfo import ZoneInfo
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from scripts.orion_backup import backup_status
from pydantic import BaseModel, Field, HttpUrl, ValidationError

from core.approvals import decision_history, pending_approvals
from core.agenda import build_agenda, export_calendar, save_appointment
from core.business_imports import BusinessImports
from core.ceo_brief import CEOBrief
from core.ceo_jobs import CEOJobs
from core.dashboard_search import dashboard_search
from core.dashboard_session import DashboardSessions, SESSION_LIFETIME
from core.dispatcher import Dispatcher
from core.llm import LLMError, LLMManager
from core.inbox import Inbox
from core.inbox_accounts import InboxAccounts
from core.inbox_media import extract_media
from core.local_operations import BriefJournal, capability_report, service_health
from core.memory import Memory
from core.n8n_access import USERNAME as N8N_USERNAME, authorized as n8n_authorized
from core.orchestrator import Orchestrator
from core.planner import Planner
from core.projects import Projects
from core.registry import AgentRegistry
from core.semantic_memory import SemanticMemory
from core.site_operations import SiteOperations, site_templates
from core.support import Support
from core.wedding import wedding_plan, wedding_templates
from core.wedding_dossier import WeddingDossier
from core.wedding_notes import WeddingNotes
from core.wedding_mail import reminder_message_id, send_reminder, smtp_config
from core.wedding_checklist import OPTIONS, WeddingChecklist

ROOT = Path(__file__).resolve().parents[1]
app = FastAPI(title="ORION AI")
dashboard_sessions = DashboardSessions()


inbox_basic = HTTPBasic(auto_error=False)



@lru_cache(maxsize=1)
def inbox_store():
    return Inbox(workflow_memory().path)


def inbox_accounts():
    return InboxAccounts(inbox_store())


def session_cookie(request):
    server = request.scope.get("server")
    port = server[1] if server else 8000
    return f"orion_session_{port}"


def session_identity(request):
    return dashboard_sessions.read(request.cookies.get(session_cookie(request)))


def verify_session_origin(request):
    site = request.headers.get("sec-fetch-site")
    origin = request.headers.get("origin")
    expected = f"{request.url.scheme}://{request.url.netloc}"
    if site in ("same-site", "cross-site") or (origin and origin != expected):
        raise HTTPException(status_code=403, detail="Ouvrez le tableau de bord depuis son adresse locale.")


def inbox_access(request: Request, credentials: HTTPBasicCredentials | None = Depends(inbox_basic)):
    accounts = inbox_accounts()
    if not accounts.enabled():
        return None, "local"
    if credentials:
        role = accounts.verify(credentials.username, credentials.password)
        if role:
            return credentials.username, role
    else:
        identity = session_identity(request)
        if identity:
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                verify_session_origin(request)
            return identity
    raise HTTPException(status_code=401, detail="Connectez-vous au tableau de bord.")


class DashboardLogin(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=256)


@app.get("/api/session")
def dashboard_session_status(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    identity = session_identity(request)
    return {"enabled": inbox_accounts().enabled(), "username": identity[0] if identity else None,
            "role": identity[1] if identity else None}


@app.post("/api/session")
def create_dashboard_session(body: DashboardLogin, request: Request, response: Response):
    verify_session_origin(request)
    role = inbox_accounts().verify(body.username, body.password)
    if not role:
        raise HTTPException(status_code=401, detail="Identifiants incorrects.")
    name = session_cookie(request)
    dashboard_sessions.revoke(request.cookies.get(name))
    token = dashboard_sessions.issue((body.username, role))
    response.set_cookie(name, token, max_age=SESSION_LIFETIME, httponly=True,
                        secure=request.url.scheme == "https", samesite="strict", path="/api")
    response.headers["Cache-Control"] = "no-store"
    return {"username": body.username, "role": role}


@app.delete("/api/session")
def close_dashboard_session(request: Request, response: Response):
    verify_session_origin(request)
    name = session_cookie(request)
    dashboard_sessions.revoke(request.cookies.get(name))
    response.delete_cookie(name, path="/api")
    response.headers["Cache-Control"] = "no-store"
    return {"closed": True}



def admin_access(access=Depends(inbox_access)):
    if access[1] not in ("local", "admin"):
        raise HTTPException(status_code=403, detail="Ce module est réservé à l’administrateur.")


def wedding_report_access(request: Request, credentials: HTTPBasicCredentials | None = Depends(inbox_basic)):
    if credentials and credentials.username == N8N_USERNAME:
        if os.environ.get("ORION_RECOVERY") == "1" or not n8n_authorized(workflow_memory().path, credentials.password):
            raise HTTPException(status_code=401, detail="Identifiant d’automatisation n8n invalide.")
        return True
    admin_access(inbox_access(request, credentials))
    return False


@app.get("/")
def root():
    return {"status": "running"}


def lire_profils():
    return [
        {key: getattr(agent, key) for key in ("id", "name", "team", "role", "capabilities")}
        for agent in AgentRegistry(ROOT / "agents").list()
    ]


@app.get("/api/dashboard/agents")
def dashboard_agents(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return lire_profils()


@app.get("/api/dashboard/status")
def dashboard_status(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return {
        "status": "online",
        "environment": "FastAPI local",
        "recovery": os.environ.get("ORION_RECOVERY") == "1",
        "workflows": True,
        "mode": os.environ.get("ORION_MODE", "simulation"),
        "agents": len(lire_profils()),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/dashboard/organisation")
def dashboard_organisation(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return json.loads((ROOT / "config" / "organisation.json").read_text(encoding="utf-8"))


@app.get("/api/dashboard/wedding")
def dashboard_wedding(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return wedding_templates()


class WorkflowRequest(BaseModel):
    task: str = Field(min_length=1, max_length=8000)
    agent_ids: list[str] | None = Field(default=None, max_length=5)


@lru_cache(maxsize=1)
def workflow_memory():
    return Memory(Path(os.environ.get("ORION_DB", ROOT / "memory" / "orion.sqlite3")))


def create_orchestrator(default_model="qwen2.5:7b"):
    registry = AgentRegistry(ROOT / "agents")
    llm = LLMManager(
        mode=os.environ.get("ORION_MODE", "simulation"),
        model=os.environ.get("OLLAMA_MODEL", default_model),
        endpoint=os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434"),
    )
    return Orchestrator(Planner(registry), Dispatcher(workflow_memory(), llm))


@app.post("/api/workflows", status_code=201, dependencies=[Depends(admin_access)])
def run_workflow(body: WorkflowRequest):
    orchestrator = create_orchestrator()
    try:
        return orchestrator.run(body.task, body.agent_ids)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/workflows/{workflow_id}", dependencies=[Depends(admin_access)])
def get_workflow(workflow_id: str, response: Response):
    response.headers["Cache-Control"] = "no-store"
    workflow = workflow_memory().get(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow inconnu.")
    return workflow


@lru_cache(maxsize=1)
def semantic_memory():
    database = workflow_memory().path
    default = database.with_suffix(".chroma")
    return SemanticMemory(Path(os.environ.get("ORION_CHROMA", default)))


@app.get("/api/memory/search", dependencies=[Depends(admin_access)])
def search_memory(response: Response, q: str = Query(min_length=1, max_length=500),
                  limit: int = Query(default=5, ge=1, le=20)):
    response.headers["Cache-Control"] = "no-store"
    if not q.strip():
        raise HTTPException(status_code=422, detail="Saisissez une recherche.")
    try:
        return semantic_memory().search(workflow_memory(), q.strip(), limit)
    except ImportError as error:
        raise HTTPException(status_code=503, detail="Installez ChromaDB avec requirements.txt.") from error
    except Exception as error:
        logging.getLogger(__name__).warning("Échec de recherche ChromaDB (%s)", type(error).__name__)
        raise HTTPException(status_code=503, detail="Index ChromaDB ou modèle d’embedding indisponible.") from error


@lru_cache(maxsize=1)
def wedding_store():
    database = workflow_memory().path
    return WeddingChecklist(Path(os.environ.get("ORION_WEDDING_DB", database.with_name("wedding.sqlite3"))))


class WeddingCreate(BaseModel):
    nom: str = Field(min_length=1, max_length=120)
    date_mariage: date
    options: list[str] = Field(default_factory=list, max_length=5)


class WeddingTaskUpdate(BaseModel):
    terminee: bool


def local_response(response, action):
    response.headers["Cache-Control"] = "no-store"
    try:
        return action()
    except KeyError as error:
        raise HTTPException(status_code=404, detail=error.args[0]) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/wedding/plans", dependencies=[Depends(admin_access)])
def list_wedding_plans(response: Response):
    return local_response(response, lambda: {"plans": wedding_store().list(), "options": OPTIONS})


@app.post("/api/wedding/plans", status_code=201, dependencies=[Depends(admin_access)])
def create_wedding_plan(body: WeddingCreate, response: Response):
    return local_response(response, lambda: wedding_store().create(body.nom, body.date_mariage, body.options))


@app.get("/api/wedding/plans/{plan_id}", dependencies=[Depends(admin_access)])
def read_wedding_plan(plan_id: str, response: Response):
    return local_response(response, lambda: wedding_store().get(plan_id))


class WeddingReschedule(BaseModel):
    date_mariage: date


@app.patch("/api/wedding/plans/{plan_id}", dependencies=[Depends(admin_access)])
def reschedule_wedding_plan(plan_id: str, body: WeddingReschedule, response: Response):
    return local_response(response, lambda: wedding_store().reschedule(plan_id, body.date_mariage))


@app.patch("/api/wedding/plans/{plan_id}/tasks/{task_id}", dependencies=[Depends(admin_access)])
def update_wedding_task(plan_id: str, task_id: int, body: WeddingTaskUpdate, response: Response):
    return local_response(response, lambda: wedding_store().complete(plan_id, task_id, body.terminee))


@app.get("/api/wedding/plans/{plan_id}/digest", dependencies=[Depends(admin_access)])
def wedding_digest(plan_id: str, response: Response, jours: int = Query(default=7, ge=0, le=90)):
    return local_response(response, lambda: wedding_store().digest(plan_id, date.today(), jours))


@app.get("/api/wedding/daily-report", dependencies=[Depends(wedding_report_access)])
def wedding_daily_report(response: Response, jours: int = Query(default=7, ge=0, le=90)):
    return local_response(response, lambda: {
        "date": date.today().isoformat(),
        "dossiers": wedding_store().digest_all(date.today(), jours),
    })


class WeddingContact(BaseModel):
    name: str = Field(min_length=1, max_length=160, pattern=r"\S")
    email: str = Field(default="", max_length=254, pattern=r"^(?:[^\s@,;<>?#&%]+@[^\s@,;<>?#&%]+\.[^\s@,;<>?#&%]+)?$")
    notes: str = Field(default="", max_length=4000)


class WeddingClient(WeddingContact):
    stage: Literal["prospect", "confirmed", "preparation", "event", "closed"]
    budget: int = Field(default=0, ge=0, le=10**10)


class WeddingGuest(WeddingContact):
    status: Literal["pending", "yes", "no"]
    due: date | None = None


class WeddingQuote(BaseModel):
    name: str = Field(min_length=1, max_length=160, pattern=r"\S")
    vendor: str
    status: Literal["requested", "accepted", "declined"]
    amount: int = Field(ge=0, le=10**10)
    due: date | None = None


class WeddingPayment(BaseModel):
    name: str = Field(min_length=1, max_length=160, pattern=r"\S")
    quote: str
    status: Literal["pending", "paid"]
    amount: int = Field(gt=0, le=10**10)
    due: date | None = None


class WeddingDayTask(BaseModel):
    name: str = Field(min_length=1, max_length=160, pattern=r"\S")
    responsible: str = Field(min_length=1, max_length=160, pattern=r"\S")
    time: str = Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
    status: Literal["pending", "done"]


class WeddingSummary(BaseModel):
    notes: str = Field(max_length=8000)


class WeddingRecord(BaseModel):
    kind: Literal["client", "vendor", "quote", "payment", "guest", "day", "summary"]
    id: str | None = Field(default=None, max_length=50)
    data: dict


class WeddingReminderAction(BaseModel):
    kind: Literal["quote", "payment", "guest"]
    target: str = Field(max_length=50)
    due: date
    action: Literal["approve", "dismiss", "record"]
    result: str = Field(default="", max_length=2000)


@lru_cache(maxsize=1)
def wedding_dossier():
    return WeddingDossier(wedding_store())


def wedding_today():
    return datetime.now(ZoneInfo("Europe/Paris")).date()


@app.get("/api/wedding/overview", dependencies=[Depends(admin_access)])
def wedding_overview(response: Response, jours: int = Query(default=7, ge=0, le=90)):
    return local_response(response, lambda: wedding_dossier().overview(wedding_today(), jours))


@app.post("/api/wedding/overview/relances", dependencies=[Depends(admin_access)])
def prepare_wedding_overview(response: Response, jours: int = Query(default=7, ge=0, le=90)):
    return local_response(response, lambda: wedding_dossier().overview(wedding_today(), jours, prepare=True))


@lru_cache(maxsize=1)
def brief_journal():
    return BriefJournal(workflow_memory().path)


@app.get("/api/dashboard/local-operations", dependencies=[Depends(admin_access)])
def local_operations(response: Response):
    def report():
        health = service_health()
        return {**health, "capabilities": capability_report(health),
                "brief_runs": brief_journal().latest(), "backup": backup_status()}
    return local_response(response, report)


@app.get("/api/wedding/brief", dependencies=[Depends(admin_access)])
def read_wedding_brief(response: Response, jours: int = Query(default=7, ge=0, le=90)):
    return local_response(response, lambda: wedding_dossier().latest_brief(wedding_today(), jours))


@app.post("/api/wedding/brief", status_code=201)
def create_wedding_brief(response: Response, jours: int = Query(default=7, ge=0, le=90),
                         source: Literal["dashboard", "n8n"] = "dashboard", service=Depends(wedding_report_access)):
    if service:
        source = "n8n"

    def generate():
        journal = brief_journal()
        try:
            dossier = wedding_dossier()
            result = dossier.save_brief(dossier.overview(wedding_today(), jours, prepare=True))
        except Exception:
            journal.record(source, "failed")
            raise
        journal.record(source, "completed")
        return result
    return local_response(response, generate)


@app.get("/api/wedding/plans/{plan_id}/dossier", dependencies=[Depends(admin_access)])
def read_wedding_dossier(plan_id: str, response: Response, request: Request):
    return local_response(response, lambda: {
        **wedding_dossier().read(plan_id),
        "mail": {"configured": smtp_config() is not None, "authentication": inbox_accounts().enabled() and (session_identity(request) or (None, None))[1] != "admin"},
    })


@app.put("/api/wedding/plans/{plan_id}/dossier", dependencies=[Depends(admin_access)])
def save_wedding_record(plan_id: str, body: WeddingRecord, response: Response):
    models = {"client": WeddingClient, "vendor": WeddingContact, "quote": WeddingQuote,
              "payment": WeddingPayment, "guest": WeddingGuest, "day": WeddingDayTask, "summary": WeddingSummary}
    try:
        data = models[body.kind].model_validate(body.data).model_dump(mode="json")
    except ValidationError as error:
        messages = [f"{'.'.join(map(str, item['loc']))} · {item['msg']}" for item in error.errors()]
        raise HTTPException(status_code=422, detail=" / ".join(messages)) from error
    return local_response(response, lambda: {"id": wedding_dossier().save(plan_id, body.kind, body.id, data)})


@app.post("/api/wedding/plans/{plan_id}/relances", dependencies=[Depends(admin_access)])
def detect_wedding_reminders(plan_id: str, response: Response, jours: int = Query(default=7, ge=0, le=90)):
    def detect():
        wedding_dossier().detect(plan_id, wedding_today(), jours)
        return wedding_dossier().read(plan_id)
    return local_response(response, detect)


@app.patch("/api/wedding/plans/{plan_id}/relances", dependencies=[Depends(admin_access)])
def update_wedding_reminder(plan_id: str, body: WeddingReminderAction, response: Response):
    result = body.result.strip()
    if body.action == "record" and not result:
        raise HTTPException(status_code=422, detail="Indiquez le résultat de la relance.")
    return local_response(response, lambda: wedding_dossier().transition(
        plan_id, body.kind, body.target, body.due.isoformat(), body.action, wedding_today(), result
    ))


WeddingNoteKind = Literal["decision", "meeting", "document", "idea"]


class WeddingNote(BaseModel):
    kind: WeddingNoteKind
    title: str = Field(min_length=1, max_length=180, pattern=r"\S")
    content: str = Field(min_length=1, max_length=16000, pattern=r"\S")
    source: str = Field(default="", max_length=1000)
    task_id: int | None = Field(default=None, ge=1)


@lru_cache(maxsize=1)
def wedding_notes():
    return WeddingNotes(wedding_store())


@app.get("/api/wedding/plans/{plan_id}/notes", dependencies=[Depends(admin_access)])
def search_wedding_notes(plan_id: str, response: Response, q: str = Query(default="", max_length=250),
                         kind: WeddingNoteKind | None = None,
                         limit: int = Query(default=20, ge=1, le=50),
                         offset: int = Query(default=0, ge=0)):
    return local_response(response, lambda: wedding_notes().search(plan_id, q, kind, limit, offset))


@app.post("/api/wedding/plans/{plan_id}/notes", status_code=201, dependencies=[Depends(admin_access)])
def create_wedding_note(plan_id: str, body: WeddingNote, response: Response):
    return local_response(response, lambda: {"id": wedding_notes().save(plan_id, body.model_dump())})


@app.put("/api/wedding/plans/{plan_id}/notes/{note_id}", dependencies=[Depends(admin_access)])
def update_wedding_note(plan_id: str, note_id: str, body: WeddingNote, response: Response):
    return local_response(response, lambda: {"id": wedding_notes().save(plan_id, body.model_dump(), note_id)})


class WeddingWorkflow(BaseModel):
    template_id: str = Field(max_length=100)
    brief: str = Field(default="", max_length=3000)
    note_ids: list[str] = Field(min_length=1, max_length=5)


@app.post("/api/wedding/plans/{plan_id}/workflows", status_code=201, dependencies=[Depends(admin_access)])
def run_wedding_workflow(plan_id: str, body: WeddingWorkflow, response: Response):
    def run():
        plan = wedding_plan(body.template_id, body.brief)
        sources = wedding_notes().selected(plan_id, body.note_ids)
        return create_orchestrator().run(**plan, plan_id=plan_id, sources=sources)
    return local_response(response, run)


@app.get("/api/wedding/plans/{plan_id}/workflows", dependencies=[Depends(admin_access)])
def list_wedding_workflows(plan_id: str, response: Response):
    def history():
        wedding_store().get(plan_id)
        return workflow_memory().wedding_history(plan_id)
    return local_response(response, history)


@app.get("/api/wedding/plans/{plan_id}/workflows/{workflow_id}", dependencies=[Depends(admin_access)])
def read_wedding_workflow(plan_id: str, workflow_id: str, response: Response):
    def read():
        result = workflow_memory().get(workflow_id, plan_id)
        if result is None:
            raise KeyError("Workflow introuvable dans ce dossier.")
        return result
    return local_response(response, read)


class ManagedSite(BaseModel):
    name: str = Field(min_length=1, max_length=140, pattern=r"\S")
    url: HttpUrl
    platform: str = Field(default="", max_length=140)
    repo: str = Field(default="", pattern=r"^(?:[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_][A-Za-z0-9_.-]{0,99})?$")
    objective: str = Field(default="", max_length=1000)


class SiteMission(BaseModel):
    template: str = Field(max_length=80)
    brief: str = Field(min_length=1, max_length=3000, pattern=r"\S")


class SiteDecision(BaseModel):
    action: Literal["approve", "verify", "reject"]
    result: str = Field(default="", max_length=2000)


@lru_cache(maxsize=1)
def site_operations():
    return SiteOperations(workflow_memory().path)


@app.get("/api/sites", dependencies=[Depends(admin_access)])
def list_sites(response: Response):
    return local_response(response, lambda: {
        "sites": site_operations().list(), "templates": site_templates(),
        "mode": os.environ.get("ORION_MODE", "simulation"),
    })


@app.post("/api/sites", status_code=201, dependencies=[Depends(admin_access)])
def add_site(body: ManagedSite, response: Response):
    return local_response(response, lambda: site_operations().save(body.model_dump(mode="json")))


@app.put("/api/sites/{site_id}", dependencies=[Depends(admin_access)])
def update_site(site_id: str, body: ManagedSite, response: Response):
    return local_response(response, lambda: site_operations().save(body.model_dump(mode="json"), site_id))


@app.post("/api/sites/{site_id}/github", dependencies=[Depends(admin_access)])
def sync_site(site_id: str, response: Response):
    return local_response(response, lambda: site_operations().sync(site_id))


@app.get("/api/sites/{site_id}/interventions", dependencies=[Depends(admin_access)])
def site_history(site_id: str, response: Response):
    return local_response(response, lambda: site_operations().history(site_id))


@app.post("/api/sites/{site_id}/interventions", status_code=201, dependencies=[Depends(admin_access)])
def prepare_site_intervention(site_id: str, body: SiteMission, response: Response):
    def prepare():
        store = site_operations()
        site = store.get(site_id)
        template = next((model for model in site_templates() if model["id"] == body.template), None)
        if template is None:
            raise ValueError("Workflow site inconnu.")
        context = {key: site[key] for key in ("name", "url", "platform", "repo", "objective", "github", "synced_at")}
        task = (
            template["task"] + "\n\nContexte du site : " + json.dumps(context, ensure_ascii=False)
            + "\nDemande : " + body.brief.strip()
            + "\nProduit un livrable à valider. Distingue les constats sourcés, les hypothèses et les vérifications à mener."
        )
        run = create_orchestrator().run(task, template["agent_ids"], plan_id="site:" + site_id)
        return {"intervention": store.log(site_id, body.template, run), "run": run}
    return local_response(response, prepare)


@app.get("/api/sites/{site_id}/interventions/{intervention_id}", dependencies=[Depends(admin_access)])
def read_site_intervention(site_id: str, intervention_id: str, response: Response):
    def read():
        item = site_operations().intervention(site_id, intervention_id)
        return {"intervention": item, "run": workflow_memory().get(item["workflow_id"], "site:" + site_id)}
    return local_response(response, read)


@app.patch("/api/sites/{site_id}/interventions/{intervention_id}", dependencies=[Depends(admin_access)])
def update_site_intervention(site_id: str, intervention_id: str, body: SiteDecision, response: Response):
    result = body.result.strip()
    if body.action == "verify" and not result:
        raise HTTPException(status_code=422, detail="Indiquez l’action réalisée et le résultat du contrôle.")
    if body.action == "reject" and not result:
        raise HTTPException(status_code=422, detail="Indiquez le motif du refus.")
    return local_response(response, lambda: site_operations().advance(site_id, intervention_id, body.action, result))


InboxKind = Literal["note", "document", "meeting", "transcript", "decision"]
INBOX_SCOPE = r"^(?:unfiled|(?:wedding|site|project):[a-f0-9]{32})?$"


class InboxEntry(BaseModel):
    kind: InboxKind
    title: str = Field(min_length=1, max_length=180, pattern=r"\S")
    content: str = Field(min_length=1, max_length=50000, pattern=r"\S")
    source: str = Field(default="", max_length=1000)
    source_date: date | None = None
    target_kind: Literal["wedding", "site", "project"] | None = None
    target_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    due_date: date | None = None


class InboxImport(InboxEntry):
    content: str = Field(default="", max_length=50000)


class InboxQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=1000, pattern=r"\S")
    query: str = Field(default="", max_length=250)
    scope: str = Field(default="", pattern=INBOX_SCOPE)




def inbox_owner(access):
    user, role = access
    return user if role == "member" else None


def check_project_memory_access(access):
    if access[1] == "member":
        raise HTTPException(status_code=403, detail="La mémoire des projets est réservée à l’administrateur.")


def save_inbox_entry(body, access, entry_id=None, attachment=None):
    if bool(body.target_id) != bool(body.target_kind):
        raise ValueError("Choisissez un dossier valide ou laissez l’élément à classer.")
    if body.target_kind in ("wedding", "site", "project"):
        if access[1] == "member":
            previous = inbox_store().get(entry_id, access[0]) if entry_id else None
            if not previous or (previous["target_kind"], previous["target_id"]) != (body.target_kind, body.target_id):
                raise HTTPException(status_code=403, detail="Les dossiers métier sont réservés à l’administrateur.")
        elif body.target_kind == "wedding":
            wedding_store().get(body.target_id)
        elif body.target_kind == "site":
            site_operations().get(body.target_id)
        else:
            project_store().require(body.target_id)
    owner = inbox_owner(access) if entry_id else access[0]
    return {"id": inbox_store().save(body.model_dump(mode="json"), entry_id,
                                     owner=owner, attachment=attachment)}


@app.get("/api/inbox/session")
def inbox_session(response: Response, access=Depends(inbox_access)):
    return local_response(response, lambda: {"username": access[0], "role": access[1]})


@app.get("/api/inbox")
def search_inbox(response: Response, q: str = Query(default="", max_length=250),
                 kind: InboxKind | None = None,
                 scope: str = Query(default="", pattern=INBOX_SCOPE),
                 limit: int = Query(default=20, ge=1, le=50),
                 offset: int = Query(default=0, ge=0), access=Depends(inbox_access)):
    if scope.startswith("project:"):
        check_project_memory_access(access)
    return local_response(response, lambda: inbox_store().search(q, kind, scope, limit, offset, inbox_owner(access)))


@app.get("/api/inbox/targets")
def inbox_targets(response: Response, access=Depends(inbox_access)):
    def targets():
        if access[1] == "member":
            return []
        return [
            {"id": row["id"], "kind": "wedding", "name": row["nom"]}
            for row in wedding_store().list()
        ] + [
            {"id": row["id"], "kind": "site", "name": row["name"]}
            for row in site_operations().list()
        ] + [
            {"id": row["id"], "kind": "project", "name": row["title"]}
            for row in project_store().list()
        ]
    return local_response(response, targets)


@app.get("/api/inbox/export")
def export_inbox(response: Response, access=Depends(inbox_access)):
    response.headers["Content-Disposition"] = 'attachment; filename="orion-memoire.json"'
    return local_response(response, lambda: {"version": 1, "items": inbox_store().export(inbox_owner(access))})


@app.post("/api/inbox", status_code=201)
def create_inbox_entry(body: InboxEntry, response: Response, access=Depends(inbox_access)):
    return local_response(response, lambda: save_inbox_entry(body, access))


@app.put("/api/inbox/{entry_id}")
def update_inbox_entry(entry_id: str, body: InboxEntry, response: Response, access=Depends(inbox_access)):
    return local_response(response, lambda: save_inbox_entry(body, access, entry_id))


@app.post("/api/inbox/import", status_code=201)
def import_inbox_file(response: Response, metadata: str = Form(), file: UploadFile = File(),
                      access=Depends(inbox_access)):
    try:
        entry = InboxImport.model_validate_json(metadata)
    except ValidationError as error:
        raise HTTPException(status_code=422, detail="Vérifiez le titre, les dates et le dossier.") from error
    with file.file as stream:
        payload = stream.read(16 * 1024 * 1024 + 1)
    if len(payload) > 16 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Le fichier dépasse 16 Mio.")

    def receive():
        name, mime, extracted, warning = extract_media(file.filename or "", payload)
        entry.content = entry.content.strip() or extracted
        entry.source = entry.source or name
        return {**save_inbox_entry(entry, access, attachment=(name, mime, payload)), "warning": warning}
    return local_response(response, receive)


@app.get("/api/inbox/{entry_id}/attachment")
def download_inbox_file(entry_id: str, access=Depends(inbox_access)):
    try:
        attachment = inbox_store().attachment(entry_id, inbox_owner(access))
    except KeyError as error:
        raise HTTPException(status_code=404, detail=error.args[0]) from error
    return Response(attachment["payload"], media_type="application/octet-stream", headers={
        "Content-Disposition": "attachment; filename*=UTF-8''" + quote(attachment["filename"], safe=""),
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
    })


@app.post("/api/inbox/question")
def answer_inbox_question(body: InboxQuestion, response: Response, access=Depends(inbox_access)):
    def answer():
        if body.scope.startswith("project:"):
            check_project_memory_access(access)
        if not body.scope and not body.query.strip():
            raise ValueError("Choisissez un dossier ou précisez les mots-clés des sources.")
        rows = inbox_store().search(body.query, None, body.scope, 15, 0, inbox_owner(access))["items"]
        sources = [
            {"id": row["id"], "title": row["title"], "source": row["source"],
             "date": row["source_date"], "content": row["content"][:3500]}
            for row in rows if row["content"].strip()
        ][:5]
        if not sources:
            return {"answer": "Aucun texte correspondant dans la mémoire.", "sources": []}
        if os.environ.get("ORION_MODE") != "ollama":
            raise HTTPException(status_code=503, detail="Activez le mode Ollama pour interroger la mémoire.")
        llm = LLMManager(mode="ollama", model=os.environ.get("OLLAMA_MODEL", "qwen2.5:7b"),
                         endpoint=os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434"))
        agent = AgentRegistry(ROOT / "agents").get("orion")
        task = ("Réponds uniquement à partir des sources fournies. Cite au moins une référence [S1], etc. "
                "Si les sources ne répondent pas à la question, signale-le et cite celles examinées. "
                "N’invente aucune date. Question : " + body.question)
        try:
            result = llm.complete(agent, task, [], sources)
        except LLMError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        cited = set(re.findall(r"\[S(\d+)\]", result))
        if not cited or not cited <= {str(number) for number in range(1, len(sources) + 1)}:
            raise HTTPException(status_code=502, detail="Ollama a renvoyé des références non vérifiables. Reformulez la question.")
        return {"answer": result, "sources": [
            {**source, "reference": f"S{index}"} for index, source in enumerate(sources, 1)
            if str(index) in cited
        ]}
    return local_response(response, answer)


@app.get("/api/inbox/{entry_id}")
def read_inbox_entry(entry_id: str, response: Response, access=Depends(inbox_access)):
    return local_response(response, lambda: inbox_store().get(entry_id, inbox_owner(access)))


@lru_cache(maxsize=1)
def ceo_briefs():
    return CEOBrief(workflow_memory().path)




def generate_ceo_brief(today):
    custom_imports = os.environ.get("ORION_IMPORT_DIR")
    directory = Path(custom_imports) if custom_imports else ROOT / "imports"
    return ceo_briefs().generate(today, wedding_dossier, site_operations, inbox_store,
                                 business_imports, project_store, directory, bool(custom_imports))


@lru_cache(maxsize=1)
def ceo_jobs():
    return CEOJobs(workflow_memory().path)


@app.get("/api/ceo/jobs", dependencies=[Depends(admin_access)])
def list_ceo_jobs(response: Response, background: BackgroundTasks):
    jobs = ceo_jobs()
    rows = jobs.list()
    for row in rows:
        if row["state"] == "queued":
            background.add_task(jobs.run, row["id"], generate_ceo_brief)
    return local_response(response, lambda: rows)


@app.post("/api/ceo/jobs", status_code=202, dependencies=[Depends(admin_access)])
def queue_ceo_job(response: Response, background: BackgroundTasks):
    jobs = ceo_jobs()
    job = jobs.enqueue(wedding_today(), "dashboard")
    background.add_task(jobs.run, job["id"], generate_ceo_brief)
    return local_response(response, lambda: job)


@app.get("/api/ceo/brief", dependencies=[Depends(admin_access)])
def get_ceo_brief(response: Response):
    return local_response(response, lambda: ceo_briefs().history(wedding_today()))


@app.post("/api/ceo/brief", status_code=201, dependencies=[Depends(admin_access)])
def save_ceo_brief(response: Response):
    jobs = ceo_jobs()
    job = jobs.enqueue(wedding_today(), "api")
    report = jobs.run(job["id"], generate_ceo_brief)
    if report is None:
        raise HTTPException(status_code=409, detail="Brief en cours ou génération interrompue. Consultez le journal.")
    return local_response(response, lambda: report)


class BusinessCSV(BaseModel):
    content: str = Field(min_length=1, max_length=1500000)


BusinessKind = Literal["prospects", "appointments", "tickets", "receipts"]


@lru_cache(maxsize=1)
def business_imports():
    return BusinessImports(workflow_memory().path)


@app.get("/api/ceo/imports", dependencies=[Depends(admin_access)])
def read_business_imports(response: Response):
    return local_response(response, lambda: business_imports().latest())


@app.post("/api/ceo/imports/{kind}", dependencies=[Depends(admin_access)])
def import_business_csv(kind: BusinessKind, body: BusinessCSV, response: Response):
    return local_response(response, lambda: business_imports().import_csv(kind, body.content))


class WeddingMailRequest(BaseModel):
    kind: Literal["quote", "payment", "guest"]
    target: str = Field(max_length=50)
    due: date
    confirm: Literal[True]


@app.post("/api/wedding/plans/{plan_id}/relances/mail")
def send_wedding_reminder(plan_id: str, body: WeddingMailRequest, response: Response,
                          access=Depends(inbox_access)):
    if access[1] not in ("local", "admin"):
        raise HTTPException(status_code=403, detail="L’envoi est réservé à l’administrateur.")
    config = smtp_config()
    if config is None:
        raise HTTPException(status_code=503, detail="Le service SMTP n’est pas configuré.")

    def send():
        store = wedding_dossier()
        key = (plan_id, body.kind, body.target, body.due.isoformat())
        message_id = reminder_message_id()
        reminder = store.reserve_mail(key, wedding_today(), message_id)
        try:
            outcome, detail = send_reminder(config, reminder, message_id)
        except Exception:
            logging.getLogger(__name__).exception("Échec du transport SMTP Wedding")
            outcome, detail = "unknown", "Résultat incertain. Vérifiez la messagerie avant toute nouvelle relance."
        return store.finish_mail(key, message_id, outcome, detail)
    return local_response(response, send)


SupportStatus = Literal["open", "urgent", "closed"]


class SupportUpdate(BaseModel):
    status: SupportStatus
    note: str = Field(min_length=1, max_length=2000, pattern=r"\S")


class SupportCreate(SupportUpdate):
    title: str = Field(min_length=1, max_length=240, pattern=r"\S")


def support_access(access=Depends(inbox_access)):
    if access[1] not in ("local", "admin"):
        raise HTTPException(status_code=403, detail="Le support est réservé à l’administrateur.")
    return access[0] or "Utilisateur local"


@app.get("/api/support", dependencies=[Depends(support_access)])
def list_support(response: Response, status: Literal["all", "active", "open", "urgent", "closed"] = "active",
                 limit: int = Query(default=30, ge=1, le=50), offset: int = Query(default=0, ge=0)):
    return local_response(response, lambda: Support(business_imports()).list(status, limit, offset))


@app.post("/api/support", status_code=201)
def create_support(body: SupportCreate, response: Response, actor=Depends(support_access)):
    return local_response(response, lambda: Support(business_imports()).create(
        body.title.strip(), wedding_today().isoformat(), body.status, body.note.strip(), actor))


@app.get("/api/support/ticket", dependencies=[Depends(support_access)])
def read_support(response: Response, id: str = Query(min_length=1, max_length=120)):
    return local_response(response, lambda: Support(business_imports()).get(id))


@app.patch("/api/support/ticket")
def update_support(body: SupportUpdate, response: Response, id: str = Query(min_length=1, max_length=120),
                   actor=Depends(support_access)):
    return local_response(response, lambda: Support(business_imports()).update(id, body.status, body.note.strip(), actor))


@app.get("/api/finance/receipts", dependencies=[Depends(admin_access)])
def finance_receipts(response: Response, days: Literal["30", "60", "90"] = "30",
                     status: Literal["all", "paid", "pending", "cancelled"] = "all",
                     limit: int = Query(default=30, ge=1, le=50), offset: int = Query(default=0, ge=0)):
    return local_response(response, lambda: business_imports().finances(
        wedding_today(), int(days), status, limit, offset))


ProjectStatus = Literal["planned", "active", "blocked", "done"]


class ProjectUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=180, pattern=r"\S")
    owner: str = Field(min_length=1, max_length=140, pattern=r"\S")
    due: date | None = None
    status: ProjectStatus
    note: str = Field(default="", max_length=2000)


@lru_cache(maxsize=1)
def project_store():
    return Projects(workflow_memory().path)


@app.get("/api/projects", dependencies=[Depends(admin_access)])
def list_projects(response: Response, status: ProjectStatus | Literal["all"] = "all"):
    return local_response(response, lambda: project_store().list(status))


@app.get("/api/projects/planning", dependencies=[Depends(admin_access)])
def project_planning(response: Response,
                     mode: Literal["all", "overdue", "upcoming", "blocked", "undated"] = "all",
                     owner: str = Query(default="", max_length=140),
                     limit: int = Query(default=40, ge=1, le=50), offset: int = Query(default=0, ge=0)):
    return local_response(response, lambda: project_store().planning(
        wedding_today(), mode, owner, limit, offset))


@app.get("/api/projects/{key}", dependencies=[Depends(admin_access)])
def read_project(key: str, response: Response):
    return local_response(response, lambda: project_store().get(key))


def project_fields(body):
    data = body.model_dump(mode="json")
    for field in ("title", "owner", "note"):
        data[field] = data[field].strip()
    if data["status"] == "blocked" and not data["note"]:
        raise ValueError("Indiquez le blocage à traiter.")
    return data


def save_project(body, access, key=None):
    return project_store().save(project_fields(body), access[0] or "Utilisateur local", key)


@app.post("/api/projects", status_code=201, dependencies=[Depends(admin_access)])
def create_project(body: ProjectUpdate, response: Response, access=Depends(inbox_access)):
    return local_response(response, lambda: save_project(body, access))


@app.put("/api/projects/{key}", dependencies=[Depends(admin_access)])
def update_project(key: str, body: ProjectUpdate, response: Response, access=Depends(inbox_access)):
    return local_response(response, lambda: save_project(body, access, key))


@app.get("/api/dashboard/overview", dependencies=[Depends(admin_access)])
def business_overview(response: Response, days: Literal["30", "60", "90"] = "30"):
    def overview():
        today = wedding_today()
        business = business_imports()
        receipts = business.finances(today, int(days), "all", 1, 0)
        projects = project_store().list()
        history = ceo_briefs().history(today)
        brief = history["latest"]
        return {
            "date": today.isoformat(),
            "period": {"start": receipts["start"], "end": receipts["end"]},
            "receipts": receipts["metrics"]["paid"], "receipts_source": receipts["source"],
            "tickets": business.open_tickets(),
            "projects": sum(row["status"] != "done" for row in projects),
            "blocked_projects": sum(row["status"] == "blocked" for row in projects),
            "weddings": len(wedding_store().list()),
            "sites": len(site_operations().list()),
            "brief": None if brief is None else {
                "date": brief["date"], "saved_at": brief["saved_at"],
                "count": brief["count"], "urgent": brief["urgent"],
                "items": brief["items"][:6], "sources": brief["sources"],
                "file_errors": sum(item["state"] == "error" for item in brief.get("file_sync", {}).values()),
            },
        }
    return local_response(response, overview)


class ProjectTaskUpdate(ProjectUpdate):
    dependencies: list[str] | None = None


@app.post("/api/projects/{key}/tasks", status_code=201, dependencies=[Depends(admin_access)])
def create_project_task(key: str, body: ProjectTaskUpdate, response: Response, access=Depends(inbox_access)):
    return local_response(response, lambda: project_store().save_task(
        key, project_fields(body), access[0] or "Utilisateur local", dependencies=body.dependencies))


@app.put("/api/projects/{key}/tasks/{task}", dependencies=[Depends(admin_access)])
def update_project_task(key: str, task: str, body: ProjectTaskUpdate, response: Response,
                        access=Depends(inbox_access)):
    return local_response(response, lambda: project_store().save_task(
        key, project_fields(body), access[0] or "Utilisateur local", task, body.dependencies))


@app.get("/api/projects/{key}/memory", dependencies=[Depends(admin_access)])
def project_memory(key: str, response: Response):
    def linked():
        project_store().require(key)
        return inbox_store().linked_project(key)
    return local_response(response, linked)


AgendaKind = Literal["all", "appointment", "wedding", "project", "task"]


def agenda_events(start, days, kind, limit=500, include_cancelled=False):
    project_store()
    return build_agenda(start or wedding_today(), days, kind, business_imports(), wedding_dossier(), limit, include_cancelled)


@app.get("/api/agenda", dependencies=[Depends(admin_access)])
def agenda(response: Response, start: date | None = None, days: int = Query(default=30, ge=1, le=90),
           kind: AgendaKind = "all", include_cancelled: bool = False):
    return local_response(response, lambda: agenda_events(start, days, kind, include_cancelled=include_cancelled))


@app.get("/api/agenda/export.ics", dependencies=[Depends(admin_access)])
def calendar_download(response: Response, start: date | None = None, days: int = Query(default=30, ge=1, le=90),
                      kind: AgendaKind = "all"):
    data = local_response(response, lambda: agenda_events(start, days, kind, limit=None))
    return Response(export_calendar(data["items"]), media_type="text/calendar; charset=utf-8", headers={
        "Cache-Control": "no-store",
        "Content-Disposition": f'attachment; filename="orion-agenda-{data["start"]}.ics"',
        "X-Content-Type-Options": "nosniff",
    })


@app.get("/api/agenda/targets", dependencies=[Depends(admin_access)])
def agenda_targets(response: Response):
    return local_response(response, lambda: [
        {"kind": "project", "id": row["id"], "label": row["title"]}
        for row in project_store().list()
    ] + [
        {"kind": "wedding", "id": row["id"], "label": row["nom"]}
        for row in wedding_store().list()
    ])


class LocalAppointment(BaseModel):
    title: str = Field(min_length=1, max_length=240, pattern=r"\S")
    day: date
    clock: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    duration: int = Field(default=60, ge=5, le=1440)
    note: str = Field(default="", max_length=2000)
    status: Literal["scheduled", "cancelled"] = "scheduled"
    target_kind: Literal["project", "wedding"] | None = None
    target_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


def save_local_appointment(body, key=None):
    if bool(body.target_id) != bool(body.target_kind):
        raise ValueError("Choisissez un dossier associé valide ou laissez le rendez-vous sans dossier.")
    if body.target_kind == "project":
        project_store().require(body.target_id)
    elif body.target_kind == "wedding":
        wedding_store().get(body.target_id)
    return save_appointment(business_imports(), body.model_dump(), key)


@app.post("/api/agenda/appointments", status_code=201, dependencies=[Depends(admin_access)])
def add_appointment(body: LocalAppointment, response: Response):
    return local_response(response, lambda: save_local_appointment(body))


@app.put("/api/agenda/appointments/{key}", dependencies=[Depends(admin_access)])
def update_appointment(key: str, body: LocalAppointment, response: Response):
    return local_response(response, lambda: save_local_appointment(body, key))


@app.get("/api/approvals", dependencies=[Depends(admin_access)])
def approvals(response: Response, stage: Literal["pending", "followup", "history"] = "pending"):
    def list_approvals():
        args = wedding_today(), wedding_dossier(), site_operations(), site_templates()
        return decision_history(*args) if stage == "history" else pending_approvals(*args, stage)
    return local_response(response, list_approvals)


@app.get("/api/dashboard/search", dependencies=[Depends(admin_access)])
def search_dashboard(response: Response, q: str = Query(min_length=1, max_length=150),
                     kind: Literal["all", "project", "task", "ticket", "document", "site", "wedding"] = "all",
                     limit: int = Query(default=40, ge=1, le=50)):
    def search():
        project_store()
        inbox_store()
        site_operations()
        return dashboard_search(q, kind, limit, business_imports().connect, wedding_store().connect)
    return local_response(response, search)


app.mount(
    "/dashboard",
    StaticFiles(directory=ROOT / "frontend" / "dashboard", html=True),
    name="dashboard",
)
