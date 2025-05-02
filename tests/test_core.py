import asyncio
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from models import Request, OopsResponse, Oops, Tags  # <--- 改回绝对导入
from core import OopsNote # <--- 改回绝对导入

# pytest 标记，所有测试都是异步的
pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_env(mocker):
    """模拟 Env 配置"""
    mock = MagicMock()
    mock.api_mode = "GEMINI" # 或者 "OPENAI"
    mock.api_key = "fake_api_key"
    mock.model = "fake_model"
    mock.prompt = "fake_prompt"
    mock.telegram_token = "fake_token"
    mock.mongo_uri = "mongodb://fake:27017/"
    mock.database_name = "FakeDB"
    mock.openai_endpoint = None
    # 如果 Env 有其他属性，也在这里模拟
    return mock

@pytest.fixture
def mock_generator(mocker):
    """模拟 AI 生成器"""
    mock = MagicMock()
    # 模拟 generate 方法返回一个固定的 OopsResponse
    mock.generate.return_value = OopsResponse(
        problem="模拟题目",
        answer="模拟答案",
        analysis="模拟分析",
        tags=Tags(
            problem=Tags.Problem(subject="模拟学科", question_type="模拟题型", difficulty="模拟难度", knowledge_point=["模拟知识点"]),
            answer=Tags.Answer(answer_status="模拟状态", error_type="模拟错误类型", correction_status="模拟订正状态")
        )
    )
    return mock

@pytest.fixture
def mock_saver(mocker):
    """模拟数据库保存器"""
    mock = MagicMock()
    # 模拟 save_oops 方法
    mock.save_oops = MagicMock()
    return mock

@pytest.fixture
def mock_bot(mocker):
    """模拟 Telegram Bot"""
    mock = MagicMock()
    mock.run = AsyncMock() # 模拟异步 run 方法
    return mock

@pytest_asyncio.fixture # <--- 换成这个！ ✨
async def oops_note_instance(mocker, mock_env, mock_generator, mock_saver, mock_bot):
    """创建一个带有模拟依赖的 OopsNote 实例"""
    # Patch 掉 __init__ 中创建的实例
    with patch('core.Env', return_value=mock_env), \
         patch('core.generate.Generate', return_value=mock_generator), \
         patch('core.MongoSaver', return_value=mock_saver), \
         patch('core.telegram_bot.Bot', return_value=mock_bot), \
         patch('core.OopsNote._load_queue'): # 阻止加载队列文件
        instance = OopsNote()
        # 确保实例使用的是模拟对象
        instance.Generator = mock_generator
        instance.Saver = mock_saver
        instance.Bot = mock_bot
        # 清空可能由 _load_queue (即使被 patch) 意外放入的项
        while not instance.queue.empty():
            instance.queue.get_nowait()
            instance.queue.task_done()
        yield instance # 返回实例供测试使用
        # 清理：确保队列为空，防止影响其他测试
        while not instance.queue.empty():
            instance.queue.get_nowait()
            instance.queue.task_done()


async def test_deal_request_success(oops_note_instance, mock_generator, mock_saver):
    """测试 deal_request 成功处理一个请求"""
    # 准备一个假的请求
    fake_image_bytes = b'fakeimagedata'
    fake_image_path = "/fake/path/image.jpg"
    fake_prompt = "分析这张图片"
    test_request = Request(image=fake_image_bytes, image_path=fake_image_path, prompt=fake_prompt)

    # 把假请求放入队列
    await oops_note_instance.queue.put(test_request)
    # 添加一个 None 来停止 deal_request 循环（或者使用 asyncio.wait_for）
    await oops_note_instance.queue.put(None)

    # 运行 deal_request (不需要运行整个 launch)
    # 使用 wait_for 确保它不会永远运行下去
    try:
        await asyncio.wait_for(oops_note_instance.deal_request(), timeout=1.0)
    except asyncio.TimeoutError:
        pytest.fail("deal_request timed out")

    # --- 断言 ---
    # 1. 检查 Generator.generate 是否被调用了一次，并且参数正确
    mock_generator.generate.assert_called_once_with(test_request)

    # 2. 检查 Saver.save_oops 是否被调用了一次
    mock_saver.save_oops.assert_called_once()

    # 3. 检查传递给 save_oops 的参数是否符合预期
    #    获取传递给 save_oops 的第一个参数 (Oops 对象)
    call_args, _ = mock_saver.save_oops.call_args
    saved_oops_instance = call_args[0]

    #    验证 saved_oops_instance 的属性
    assert isinstance(saved_oops_instance, Oops)
    assert saved_oops_instance.problem == "模拟题目"
    assert saved_oops_instance.answer == "模拟答案"
    assert saved_oops_instance.analysis == "模拟分析"
    assert saved_oops_instance.tags.problem.subject == "模拟学科"
    assert saved_oops_instance.image_path == fake_image_path # 确保 image_path 被正确传递

    # 4. 检查队列是否为空 (因为 None 也被处理了)
    assert oops_note_instance.queue.empty()


async def test_deal_request_generator_exception(oops_note_instance, mock_generator, mock_saver, caplog):
    """测试 AI 生成器抛出异常时的情况"""
    # 让 generate 方法抛出异常
    mock_generator.generate.side_effect = Exception("AI 炸了！")

    # 准备请求
    test_request = Request(image=b'fake', image_path="/fake/path", prompt="分析")
    await oops_note_instance.queue.put(test_request)
    await oops_note_instance.queue.put(None) # 停止信号

    # 运行
    try:
        await asyncio.wait_for(oops_note_instance.deal_request(), timeout=1.0)
    except asyncio.TimeoutError:
        pytest.fail("deal_request timed out")

    # --- 断言 ---
    # 1. generate 被调用了
    mock_generator.generate.assert_called_once_with(test_request)

    # 2. save_oops 没有被调用
    mock_saver.save_oops.assert_not_called()

    # 3. 检查是否有错误日志 (需要 pytest-logger 或配置 caplog)
    #    使用 pytest 内置的 caplog fixture
    assert "处理请求 (Prompt: 分析) 时发生错误: AI 炸了！" in caplog.text
    assert oops_note_instance.queue.empty()

# --- 你还可以添加更多测试 ---
# - 测试 Saver 抛出异常的情况
# - 测试队列加载/保存 (_load_queue, _save_queue) - 这需要 mock 文件操作
# - 测试 shutdown 逻辑 - 这需要 mock asyncio.gather 和 task.cancel