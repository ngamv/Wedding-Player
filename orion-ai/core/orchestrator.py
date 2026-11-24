class Orchestrator:
    def __init__(self, planner, dispatcher):
        self.planner = planner
        self.dispatcher = dispatcher

    def run(self, task, agent_ids=None, *, plan_id=None, sources=()):
        return self.dispatcher.execute(task, self.planner.plan(task, agent_ids), plan_id=plan_id, sources=sources)
