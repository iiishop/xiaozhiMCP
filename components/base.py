from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class MCPComponent(ABC):
    @abstractmethod
    def register(self, mcp: Any) -> None:
        raise NotImplementedError
