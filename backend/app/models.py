"""⚠️ 已弃用：该文件已拆分为子模块。

请改为从 `app.models` 导入，例如：
`from app.models import TaskRecord, ProblemBlock, SolutionBlock`
"""

import warnings

# 为向后兼容重新导出 models 包全部符号
from .models import *  # noqa: F401, F403

warnings.warn(
    "从 app.models.py 导入已弃用，请改用 `from app.models import ...`。",
    DeprecationWarning,
    stacklevel=2,
)
