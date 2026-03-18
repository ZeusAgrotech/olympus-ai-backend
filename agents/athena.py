from .agent import Agent
from models.athena import AthenaModel


class AthenaAgent(Agent):
    """Agente declarativo dedicado ao planner Athena — análise estratégica e raciocínio profundo."""

    model = AthenaModel
    model_aliases = ["athena"]
    owned_by = "zeus"
    hidden = False
