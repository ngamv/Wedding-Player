import re


class TaskRouter:
    def route(self, task, registry):
        text = re.sub(r"[^\w]+", " ", task.casefold().replace("_", " "))

        def score(agent):
            return sum(
                f" {cap.casefold().replace('_', ' ')} " in f" {text} "
                for cap in agent.capabilities
            )

        agents = registry.list()
        candidat = max(agents, key=score)
        return candidat if score(candidat) else registry.get("orion")
