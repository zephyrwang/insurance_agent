"""
Actor — who is asking.

Threaded through SupervisorAgent.run() into agent/tool construction so access control is a
code seam (the server decides what an actor can see), never a prompt instruction.
"""

from dataclasses import dataclass
from typing import Literal, Optional


@dataclass(frozen=True)
class Actor:
    mode: Literal["staff", "carrier"]
    carrier_name: Optional[str] = None

    @staticmethod
    def staff() -> "Actor":
        return Actor(mode="staff")

    @staticmethod
    def carrier(carrier_name: str) -> "Actor":
        return Actor(mode="carrier", carrier_name=carrier_name)
