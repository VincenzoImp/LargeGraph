"""CPU-only exploration of graphs larger than RAM."""

from ._version import __version__
from .api import Analysis, analyze
from .config import AnalysisOptions
from .runtime import Resources

__all__ = ["__version__", "Analysis", "AnalysisOptions", "Resources", "analyze"]
