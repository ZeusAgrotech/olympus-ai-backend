from .agent import Agent
from models.saori import SaoriModel


class SaoriAgent(Agent):
    """Agente declarativo dedicado ao planner Saori — respostas rápidas e uso cotidiano."""

    model = SaoriModel
    model_aliases = ["saori"]
    owned_by = "zeus"
    hidden = False
