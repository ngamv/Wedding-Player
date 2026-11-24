from .task_router import TaskRouter


class Planner:
    def __init__(self, registry):
        self.registry = registry
        self.router = TaskRouter()

    def plan(self, task: str, agent_ids: list[str] | None = None):
        if not task.strip() or len(task) > 8000:
            raise ValueError("La demande doit contenir entre 1 et 8 000 caractères.")
        if agent_ids is None:
            return (self.router.route(task, self.registry),)
        if not 1 <= len(agent_ids) <= 5 or len(set(agent_ids)) != len(agent_ids):
            raise ValueError("Choisissez entre 1 et 5 agents distincts.")
        return tuple(self.registry.get(agent_id) for agent_id in agent_ids)
