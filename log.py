import logging
# 启用日志记录，但禁用HTTP连接日志
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# 设置httpx和telegram.request的日志级别为WARNING或更高，以禁用HTTP请求日志
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.request").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)