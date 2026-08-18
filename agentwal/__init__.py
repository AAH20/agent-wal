"""
Agent-WAL: The Embedded Write-Ahead Logging & Deterministic Replay Engine.
"""

from agentwal.core import (
    AgentWALEngine,
    DeterministicReplayEngine,
    WALRecord,
    GENESIS_HASH,
)

__all__ = [
    "AgentWALEngine",
    "DeterministicReplayEngine",
    "WALRecord",
    "GENESIS_HASH",
]

__version__ = "1.0.0"
