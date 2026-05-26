from fastapi import WebSocket


class AgentManager:
    def __init__(self):
        self._agents: dict[str, WebSocket] = {}

    async def connect(self, device_id: str, websocket: WebSocket):
        await websocket.accept()
        self._agents[device_id] = websocket

    def disconnect(self, device_id: str):
        self._agents.pop(device_id, None)

    def list_agents(self):
        return sorted(self._agents.keys())

    async def send_command(self, device_id: str, command: dict):
        websocket = self._agents.get(device_id)
        if websocket is None:
            return False

        try:
            await websocket.send_json(command)
        except Exception:
            self.disconnect(device_id)
            return False

        return True
