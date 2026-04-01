"""
Survey Agent - 学术综述自动化 Agent Pipeline

顶层包初始化，暴露核心对外接口。
"""

from survey_agent.state import SurveyState, Phase, create_initial_state
from survey_agent.workflow.graph import build_graph

__all__ = [
    "SurveyState",
    "Phase",
    "create_initial_state",
    "build_graph",
]
