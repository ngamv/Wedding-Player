from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Agent:
    id: str
    name: str
    role: str
    team: str
    capabilities: tuple[str, ...]
    system_prompt: str
    memory_enabled: bool


class AgentRegistry:
    def __init__(self, directory: Path):
        self._agents = {}
        for path in sorted(directory.glob("*/*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            fields = ("id", "name", "role", "team", "system_prompt")
            if not isinstance(data, dict) or any(
                not isinstance(data.get(key), str) or not data[key].strip() for key in fields
            ):
                raise ValueError(f"Profil incomplet : {path}")
            capabilities = data.get("capabilities")
            memory = data.get("memory_enabled", True)
            if (not isinstance(capabilities, list)
                or not all(isinstance(item, str) and item.strip() for item in capabilities)
                or not isinstance(memory, bool)
                or data["id"] != path.stem or data["team"] != path.parent.name
                or data["id"] in self._agents):
                raise ValueError(f"Profil invalide ou dupliqué : {path}")
            self._agents[data["id"]] = Agent(
                **{key: data[key] for key in fields},
                capabilities=tuple(capabilities), memory_enabled=memory,
            )
        if not self._agents:
            raise ValueError("Catalogue vide.")

    def get(self, agent_id: str) -> Agent:
        try:
            return self._agents[agent_id]
        except KeyError as error:
            raise ValueError(f"Agent inconnu : {agent_id}") from error

    def list(self) -> tuple[Agent, ...]:
        return tuple(self._agents.values())
