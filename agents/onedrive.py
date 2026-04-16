from .agent import Agent
from models.onedrive import OneDriveModel


class OneDriveAgent(Agent):
    """Agente temporário para testes da integração OneDrive via Ragie."""

    model = OneDriveModel
    owned_by = "Zeus"
    hidden = False
