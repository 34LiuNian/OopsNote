# OopsNote 后端架构文档

本文档描述 OopsNote 后端的架构设计原则和分层结构。

## 架构原则

基于 [什么是好的代码](https://soulhacker.me/posts/good-code/) 的原则：

### 核心公理

1. **内聚公理**：每个模块专注于单一职责
2. **耦合公理**：模块间依赖最小化
3. **接口公理**：
   - 责任分离：接口只暴露必要功能
   - 稳定性：接口一旦投入使用就不轻易修改
   - 契约化：定义清晰的数据类型和异常

### AI Coding 时代的不变量

- ✅ **模块化**：便于人类和 AI 理解与维护
- ✅ **可读性**：代码即文档
- ✅ **可测试性**：每个模块独立可验证

---

## 分层架构

```
┌─────────────────────────────────────────────────┐
│              API Layer (api/)                   │
│  - REST endpoints                               │
│  - Request/Response models                      │
│  - HTTP-specific logic                          │
└─────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────┐
│         Application Layer (application.py)      │
│  - Use case orchestration                       │
│  - Transaction boundaries                       │
│  - Cross-cutting concerns                       │
└─────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────┐
│          Domain Layer (domain.py)               │
│  - Business logic                               │
│  - Domain services                              │
│  - Processing pipeline                          │
└─────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────┐
│           Protocols Layer (protocols.py)        │
│  - Interface definitions                        │
│  - Dependency inversion                         │
│  - Abstract contracts                           │
└─────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────┐
│      Infrastructure Layer (services/, clients/) │
│  - Concrete implementations                     │
│  - External adapters                            │
│  - Technical details                            │
└─────────────────────────────────────────────────┘
```

---

## 模块职责

### 1. API 层 (`app/api/`)

**职责**：处理 HTTP 协议相关逻辑
- 路由定义
- 请求/响应转换
- HTTP 中间件
- 认证授权

**示例**：
```python
@router.post("/tasks", response_model=TaskResponse)
def create_task(request: Request, payload: TaskCreateRequest) -> TaskResponse:
    task = _app_svc(request).create_task(payload)
    return TaskResponse(task=task)
```

### 2. 应用层 (`app/application.py`)

**职责**：协调领域服务实现用例
- 用例编排
- 事务管理
- 跨领域关注点
- 模型转换

**特点**：
- 不包含业务逻辑
- 只协调领域服务
- 处理异常和错误

**示例**：
```python
def process_task(self, task_id: str) -> TaskRecord:
    task = self.repository.get_task(task_id)
    context = self.processing.process_task(task_id, task.payload, task.asset)
    task.status = TaskStatus.COMPLETED
    task.problems = context.problems
    self.repository.update_task(task)
    return task
```

### 3. 领域层 (`app/domain.py`)

**职责**：核心业务逻辑
- 问题提取服务
- 解题服务
- 打标服务
- 归档服务
- 流程编排

**特点**：
- 纯业务逻辑
- 不依赖具体实现
- 高度可测试

**示例**：
```python
class ExtractionService:
    def extract_problems(
        self,
        payload: TaskCreateRequest,
        asset: AssetMetadata | None = None,
    ) -> tuple[DetectionOutput, list[ProblemBlock]]:
        # 业务逻辑实现
        ...
```

### 4. 协议层 (`app/protocols.py`)

**职责**：定义接口契约
- Protocol 定义
- 依赖倒置
- 接口稳定性

**特点**：
- 只有抽象定义
- 无实现细节
- 高度稳定

**示例**：
```python
@runtime_checkable
class Extractor(Protocol):
    def run(
        self,
        payload: TaskCreateRequest,
        detection: DetectionOutput,
        asset: AssetMetadata | None = None,
    ) -> list[ProblemBlock]:
        ...
```

### 5. 基础设施层 (`app/services/`, `app/clients/`)

**职责**：具体实现
- LLM 客户端
- 文件存储
- 数据库访问
- 外部服务集成

**特点**：
- 依赖具体技术
- 可替换实现
- 通过协议注入

---

## 依赖关系

```
API 层 → 应用层 → 领域层 → 协议层 ← 基础设施层
```

**关键原则**：
- 依赖方向始终向下
- 上层依赖下层的抽象（协议）
- 下层不依赖上层

---

## 数据流

### 任务处理流程

```
1. HTTP Request (POST /tasks)
   ↓
2. API Layer: 验证请求，转换为 TaskCreateRequest
   ↓
3. Application Layer: 创建任务，启动处理
   ↓
4. Domain Layer: 执行 pipeline
   ├─ ExtractionService: 提取问题
   ├─ SolvingService: 生成解答
   ├─ TaggingService: 生成标签
   └─ ArchivingService: 归档结果
   ↓
5. Infrastructure: 持久化到存储
   ↓
6. Event Bus: 发布事件
   ↓
7. HTTP Response: 返回任务状态
```

---

## 测试策略

### 分层测试

1. **单元测试**（领域层）
   ```python
   def test_extraction_service():
       extractor = MockExtractor()
       service = ExtractionService(extractor)
       result = service.extract_problems(payload)
       assert len(result.problems) > 0
   ```

2. **集成测试**（应用层）
   ```python
   def test_process_task_use_case():
       app_service = create_test_app_service()
       task = app_service.create_task(payload)
       result = app_service.process_task(task.id)
       assert result.status == TaskStatus.COMPLETED
   ```

3. **端到端测试**（API 层）
   ```python
   def test_create_task_api():
       response = client.post("/tasks", json=payload)
       assert response.status_code == 201
       assert "task" in response.json()
   ```

---

## 扩展性

### 添加新功能

遵循开闭原则（Open-Closed Principle）：

1. **定义新协议**（如需要）
   ```python
   @runtime_checkable
   class Validator(Protocol):
       def validate(self, problem: ProblemBlock) -> bool:
           ...
   ```

2. **实现具体服务**
   ```python
   class ValidationService:
       def __init__(self, validator: Validator):
           self.validator = validator
       
       def validate_problems(self, problems: list[ProblemBlock]) -> list[ProblemBlock]:
           return [p for p in problems if self.validator.validate(p)]
   ```

3. **在用例中集成**
   ```python
   # application.py
   def process_task(self, task_id: str):
       context = self.processing.process_task(...)
       validated = self.validation.validate_problems(context.problems)
       ...
   ```

---

## 配置与依赖注入

### 依赖组装

```python
# bootstrap.py
def create_app() -> FastAPI:
    # Infrastructure
    ai_client = OpenAIClient(...)
    repository = FileTaskRepository(...)
    event_bus = EventBus()
    
    # Domain Services
    extraction = ExtractionService(LLMOcrExtractor(ai_client))
    solving = SolvingService(LLMSolver(ai_client))
    tagging = TaggingService(LLMTagger(ai_client))
    archiving = ArchivingService(FileArchiver())
    
    # Domain Orchestrator
    processing = TaskProcessingService(
        extraction, solving, tagging, archiving, repository, event_bus
    )
    
    # Application
    app_service = ApplicationService(repository, event_bus, processing)
    
    # API
    app = FastAPI()
    app.state.app_service = app_service
    return app
```

---

## 最佳实践

### 1. 单一职责

每个类/函数只做一件事：
```python
# ✅ Good
class ExtractionService:
    """专注于问题提取"""
    ...

# ❌ Bad
class TaskManager:
    """什么都做"""
    def extract(self): ...
    def solve(self): ...
    def tag(self): ...
    def save(self): ...
```

### 2. 依赖倒置

依赖抽象而非具体实现：
```python
# ✅ Good
class SolvingService:
    def __init__(self, solver: Solver):  # Protocol
        self.solver = solver

# ❌ Bad
class SolvingService:
    def __init__(self):
        self.solver = OpenAIClient()  # Concrete class
```

### 3. 接口隔离

接口要小而精：
```python
# ✅ Good
@runtime_checkable
class Solver(Protocol):
    def run(self, payload, problems) -> list[SolutionBlock]: ...

# ❌ Bad
@runtime_checkable
class AIAgent(Protocol):
    def extract(self): ...
    def solve(self): ...
    def tag(self): ...
    def chat(self): ...
    def embed(self): ...
```

### 4. 文档化

代码即文档：
```python
class ExtractionService:
    """Service for extracting problems from images.
    
    Single Responsibility: Handles all problem extraction logic,
    including OCR and manual reconstruction.
    """
    
    def extract_problems(...) -> tuple[DetectionOutput, list[ProblemBlock]]:
        """Extract problems from uploaded image.
        
        Args:
            payload: Task creation request with metadata
            asset: Optional asset metadata
            
        Returns:
            Tuple of (detection result, list of extracted problems)
        """
```

---

## 迁移指南

### 从旧架构迁移

当前架构是渐进式重构的结果。迁移步骤：

1. **保持向后兼容**：旧代码仍可运行
2. **逐步替换**：新功能使用新架构
3. **测试覆盖**：确保行为一致

---

## 参考资料

- [什么是好的代码](https://soulhacker.me/posts/good-code/)
- [Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [Domain-Driven Design](https://martinfowler.com/tags/domain%20driven%20design.html)
- [Dependency Injection](https://martinfowler.com/articles/injection.html)
