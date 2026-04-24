"""
coral/ — CORAL Shared Persistent Memory System
Compatible with orchestrator/graph/nodes.py
"""
from coral.memory import CoralMemory
from coral.heartbeat import HeartbeatRunner, HeartbeatConfig
from coral.agent_manager import AgentManager
from coral.workspace import WorkspaceManager

__all__ = ["CoralMemory", "HeartbeatRunner", "HeartbeatConfig", "AgentManager", "WorkspaceManager"]