import pytest
import asyncio
import os
import pickle
from typing import List

# 模拟 Request 类，因为它在 core 或其他地方定义
# 在测试中，我们只需要一个具有相似结构的对象即可
class MockRequest:
    def __init__(self, prompt: str, image_path: str, user_id: int):
        self.prompt = prompt
        self.image_path = image_path
        self.user_id = user_id

    # 为了让 pickle 能够序列化和反序列化，最好提供 __eq__
    def __eq__(self, other):
        if not isinstance(other, MockRequest):
            return NotImplemented
        return (self.prompt == other.prompt and
                self.image_path == other.image_path and
                self.user_id == other.user_id)

# 从你的项目中导入被测试的类
# 假设 queue_persistence.py 在项目根目录
from queue_persistence import PickleFileQueuePersistence # <--- 改回绝对导入

# --- Fixtures ---

@pytest.fixture
def temp_file(tmp_path):
    """创建一个临时文件路径供测试使用"""
    file_path = tmp_path / "test_queue_state.pkl"
    yield str(file_path) # 提供路径给测试函数
    # 测试结束后，如果文件还存在，清理掉 (虽然 load 后会自动删)
    if file_path.exists():
        file_path.unlink()

@pytest.fixture
def persistence(temp_file):
    """创建一个 PickleFileQueuePersistence 实例"""
    return PickleFileQueuePersistence(temp_file)

@pytest.fixture
def sample_items() -> List[MockRequest]:
    """创建一些模拟的请求对象"""
    return [
        MockRequest("prompt1", "/path/to/image1.jpg", 123),
        MockRequest("prompt2", "/path/to/image2.png", 456),
        MockRequest("prompt3", None, 789), # 测试 image_path 为 None 的情况
    ]

# --- Test Cases ---

def test_save_and_load_basic(persistence: PickleFileQueuePersistence, temp_file: str, sample_items: List[MockRequest]):
    """测试基本的保存和加载列表功能"""
    # 1. 保存
    success = persistence.save(sample_items)
    assert success is True
    assert os.path.exists(temp_file), "保存后文件应存在"

    # 验证文件内容 (可选，但有助于调试)
    try:
        with open(temp_file, 'rb') as f:
            loaded_raw = pickle.load(f)
        assert loaded_raw == sample_items
    except Exception as e:
        pytest.fail(f"读取pickle文件验证时出错: {e}")


    # 2. 加载
    loaded_items = persistence.load()
    assert loaded_items == sample_items, "加载后的项目应与原始项目匹配"
    assert not os.path.exists(temp_file), "加载后文件应被删除"

def test_load_non_existent_file(persistence: PickleFileQueuePersistence, temp_file: str):
    """测试加载一个不存在的文件"""
    # 确保文件一开始就不存在
    if os.path.exists(temp_file):
        os.remove(temp_file)

    loaded_items = persistence.load()
    assert loaded_items == [], "加载不存在的文件应返回空列表"

def test_save_empty_list(persistence: PickleFileQueuePersistence, temp_file: str):
    """测试保存一个空列表"""
    success = persistence.save([])
    assert success is True
    # 保存空列表通常不应该创建文件，或者创建一个空文件然后 load 时能正确处理
    # 检查 load 的行为
    loaded_items = persistence.load()
    assert loaded_items == [], "加载空状态应返回空列表"
    assert not os.path.exists(temp_file), "处理空列表后不应留下文件"


@pytest.mark.asyncio
async def test_save_and_load_queue(persistence: PickleFileQueuePersistence, temp_file: str, sample_items: List[MockRequest]):
    """测试保存和加载 asyncio.Queue 的功能"""
    # 1. 准备源队列并保存
    source_queue = asyncio.Queue()
    for item in sample_items:
        await source_queue.put(item)

    persistence.save_queue(source_queue)
    assert os.path.exists(temp_file), "保存队列后文件应存在"
    # 验证源队列在保存后是否为空 (save_queue 会清空它)
    assert source_queue.empty(), "save_queue 应该清空源队列"


    # 2. 准备目标队列并加载
    target_queue = asyncio.Queue()
    persistence.load_queue(target_queue)
    assert not os.path.exists(temp_file), "加载队列后文件应被删除"

    # 3. 验证目标队列内容
    loaded_items_from_queue = []
    while not target_queue.empty():
        item = await target_queue.get()
        loaded_items_from_queue.append(item)
        target_queue.task_done() # 标记任务完成

    assert loaded_items_from_queue == sample_items, "从队列加载的项目应与原始项目匹配"


@pytest.mark.asyncio
async def test_save_empty_queue(persistence: PickleFileQueuePersistence, temp_file: str):
    """测试保存一个空的 asyncio.Queue"""
    empty_queue = asyncio.Queue()
    persistence.save_queue(empty_queue)

    # 保存空队列不应创建文件，或者 load 时能正确处理
    assert not os.path.exists(temp_file), "保存空队列不应创建持久化文件"

    new_queue = asyncio.Queue()
    persistence.load_queue(new_queue)
    assert new_queue.empty(), "从空状态加载队列应为空"


@pytest.mark.asyncio
async def test_load_queue_non_existent_file(persistence: PickleFileQueuePersistence, temp_file: str):
    """测试从不存在的文件加载到队列"""
     # 确保文件一开始就不存在
    if os.path.exists(temp_file):
        os.remove(temp_file)

    queue = asyncio.Queue()
    persistence.load_queue(queue)
    assert queue.empty(), "从不存在的文件加载队列应为空"

