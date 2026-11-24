from datetime import date

from mcp.server.fastmcp import FastMCP

from backend.main import create_orchestrator, wedding_store
from core.wedding import wedding_plan, wedding_templates

server = FastMCP("ORION Wedding")


@server.tool()
def wedding_planner() -> list[dict]:
    """Liste les six modèles Wedding et leurs agents."""
    return wedding_templates()


@server.tool()
def wedding_prepare(template_id: str, brief: str = "") -> dict:
    """Prépare une mission et sa séquence d’agents pour validation humaine."""
    return wedding_plan(template_id, brief)


@server.tool()
def wedding_run(template_id: str, brief: str) -> dict:
    """Exécute un workflow de préparation avec le moteur local et enregistre le résultat dans SQLite."""
    if not brief.strip():
        raise ValueError("Fournissez un brief pour l’exécution.")
    plan = wedding_plan(template_id, brief)
    return create_orchestrator(default_model="qwen3:8b").run(**plan)


@server.tool()
def wedding_list_plans() -> list[dict]:
    """Liste les dossiers mariage disponibles dans SQLite."""
    return wedding_store().list()


@server.tool()
def wedding_create_checklist(nom: str, date_mariage: str, options: list[str] | None = None) -> dict:
    """Crée un dossier local. Date AAAA-MM-JJ. Options : religieuse, laique, contrat, lune_de_miel, audition."""
    return wedding_store().create(nom, date.fromisoformat(date_mariage), options or [])


@server.tool()
def wedding_read_checklist(plan_id: str) -> dict:
    """Consulte les tâches du dossier et leurs dates, ressources et prérequis."""
    return wedding_store().get(plan_id)


@server.tool()
def wedding_update_task(plan_id: str, task_id: int, terminee: bool) -> dict:
    """Met à jour le suivi local d’une tâche après confirmation de son état par l’utilisateur."""
    plan = wedding_store().complete(plan_id, task_id, terminee)
    return next(task for task in plan["tasks"] if task["id"] == task_id)


@server.tool()
def wedding_deadlines(plan_id: str, jours: int = 7) -> dict:
    """Liste les tâches passées et à venir, et indique celles bloquées par un prérequis."""
    return wedding_store().digest(plan_id, date.today(), jours)


if __name__ == "__main__":
    server.run(transport="stdio")
