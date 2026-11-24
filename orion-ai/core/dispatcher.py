from .llm import LLMError


class Dispatcher:
    def __init__(self, memory, llm):
        self.memory = memory
        self.llm = llm

    def execute(self, task, agents, *, plan_id=None, sources=()):
        workflow_id = self.memory.create(task, [agent.id for agent in agents], plan_id, sources)
        context, recorded = [], []
        try:
            for agent in agents:
                result = self.llm.complete(agent, task, context, sources)
                context.append({"agent": agent.id, "result": result})
                recorded.append({
                    "agent": agent.id,
                    "mode": self.llm.mode,
                    "result": result if agent.memory_enabled else None,
                })
                last = agent is agents[-1]
                self.memory.save(workflow_id, recorded, "completed" if last else "running")
        except LLMError as error:
            self.memory.save(workflow_id, recorded, "failed", str(error))
        return self.memory.get(workflow_id, plan_id)
