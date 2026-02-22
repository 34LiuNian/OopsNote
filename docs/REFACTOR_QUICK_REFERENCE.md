# 架构重构快速参考

## 📦 新的模块结构

### Agents 模块

```python
# 导入工具函数
from app.agents import utils

# 使用示例
utils._coerce_str(value, "default")
utils._load_prompt("solver")
utils._normalize_linebreaks(text)
```

### Models 模块

```python
# 推荐：从子模块导入
from app.models.task import TaskRecord, TaskCreateRequest
from app.models.problem import ProblemBlock, SolutionBlock, TaggingResult
from app.models.common import TaskStatus, CropRegion, OptionItem
from app.models.pipeline import PipelineResult
from app.models.library import ProblemSummary
from app.models.api import UploadRequest, OverrideProblemRequest

# 兼容：从包根导入（仍然有效）
from app.models import TaskRecord, ProblemBlock, SolutionBlock
```

## 🔧 常用工具函数

### 类型转换

```python
from app.agents import utils

# 字符串转换
utils._coerce_str(None, "default")      # -> "default"
utils._coerce_str("test")               # -> "test"

# 列表转换
utils._coerce_list(None, ["default"])   # -> ["default"]
utils._coerce_list(["a", "b"], [])      # -> ["a", "b"]
utils._coerce_str_list("single")        # -> ["single"]

# 整数转换（带边界）
utils._coerce_int("5", 0, 0, 10)        # -> 5
utils._coerce_int("invalid", 3, 0, 10)  # -> 3
```

### 文本处理

```python
# 标准化换行符
utils._normalize_linebreaks("test\r\ntest")  # -> "test\ntest"

# 占位符检测
utils._contains_placeholder("Hello {name}")  # -> True

# 提取占位符
utils._extract_placeholders("Hello {name}")  # -> ["name"]
```

### 提示词加载

```python
# 加载普通提示词
template = utils._load_prompt("solver")   # 加载 prompts/solver.md
template = utils._load_prompt("tagger")   # 加载 prompts/tagger.md

# 加载 OCR 提示词（带缓存）
template = utils._load_ocr_template()     # 加载 prompts/ocr.md
```

## 📁 模型分类速查

| 类别 | 模块 | 主要模型 |
|------|------|----------|
| **通用类型** | `models/common.py` | TaskStatus, CropRegion, OptionItem, DetectionOutput |
| **题目解答** | `models/problem.py` | ProblemBlock, SolutionBlock, TaggingResult, ArchiveRecord |
| **任务** | `models/task.py` | TaskRecord, TaskCreateRequest, TaskSummary, AssetMetadata |
| **流水线** | `models/pipeline.py` | PipelineResult |
| **题库** | `models/library.py` | ProblemSummary, ProblemsResponse, TaggingQuery |
| **API** | `models/api.py` | UploadRequest, OverrideProblemRequest, LatexCompileRequest 等 |

## ✅ 测试验证

运行冒烟测试验证重构：

```bash
cd backend
.venv\Scripts\python.exe scripts/test_refactor.py
```

预期输出：
```
============================================================
Architecture Refactoring - Smoke Tests
============================================================
Testing models imports...
  ✓ All models imported successfully
Testing agents utils...
  ✓ Agents utils working correctly
Testing agents modules...
  ✓ All agents modules imported successfully
Testing backward compatibility...
  ✓ Backward compatibility maintained
============================================================
✓ All tests passed!
```

## 🚨 常见问题

### Q: 旧的导入方式还能用吗？
A: 可以！`from app.models import TaskRecord` 仍然有效。

### Q: 需要更新现有代码吗？
A: 不需要。所有改动都是向后兼容的。

### Q: 如何导入 HttpUrl？
A: `from app.models import HttpUrl`（已重新导出）

### Q: models.py 文件去哪了？
A: 已拆分为子模块，原文件备份为 `models.py.bak`。

## 📚 详细文档

- [完整重构报告](./ARCHITECTURE_REFACTOR_REPORT.md)
- [架构文档](./ARCHITECTURE.md)
- [AI 流程说明](../AGENTS.md)
