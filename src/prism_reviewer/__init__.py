import importlib.metadata
import os
import tomllib

try:
    __version__ = importlib.metadata.version("prism-reviewer")
except importlib.metadata.PackageNotFoundError:
    try:
        _pyproject = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "pyproject.toml"))
        if os.path.exists(_pyproject):
            with open(_pyproject, "rb") as _f:
                __version__ = tomllib.load(_f).get("project", {}).get("version", "0.1.2")
        else:
            __version__ = "0.1.2"
    except Exception:
        __version__ = "0.1.2"


from .services.llm import ResilientLLMClient
from .services.github import GitHubAppBridge
from .codelens.parser import UniversalASTAnalyzer
from .agents.graph import build_graph
from .agents.state import Finding, ReviewState


__all__ = [
    "__version__",
    "ResilientLLMClient",
    "GitHubAppBridge",
    "UniversalASTAnalyzer",
    "build_graph",
    "Finding",
    "ReviewState",
]

