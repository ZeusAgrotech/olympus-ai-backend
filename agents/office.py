from .agent import Agent
from models.office import OfficeModel


class OfficeAgent(Agent):
    """Assistente para criação de documentos, slides e fórmulas no Office."""

    model = OfficeModel
    include_thought = False
    owned_by = "Zeus"
    hidden = False
