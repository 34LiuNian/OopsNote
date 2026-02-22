"""
⚠️ DEPRECATED: This file has been split into submodules.

Please import from app.models instead:
    from app.models import TaskRecord, ProblemBlock, SolutionBlock
"""

import warnings

# Re-export everything from the models package for backward compatibility
from .models import *  # noqa: F401, F403

warnings.warn(
    "Importing from app.models.py is deprecated. "
    "Please use 'from app.models import ...' instead.",
    DeprecationWarning,
    stacklevel=2,
)
