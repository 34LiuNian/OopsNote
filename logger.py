# logger.py
import logging
import coloredlogs

# 自定义日志格式
LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
LOG_LEVEL = "DEBUG"

# 全局 logger 实例（根 logger）
logger = logging.getLogger()
logger.setLevel(LOG_LEVEL)

# 添加颜色控制台输出
coloredlogs.install(level=LOG_LEVEL, logger=logger, fmt=LOG_FORMAT)

# 过滤指定模块的 DEBUG（如 telegram 或 pymongo 等）
class ModuleFilter(logging.Filter):
    def __init__(self, banned_modules):
        super().__init__()
        self.banned_modules = set(banned_modules)

    def filter(self, record):
        return all(banned not in record.name for banned in self.banned_modules)

# 指定要屏蔽 DEBUG 日志的模块
banned_debug_modules = ['telegram.ext', 'pymongo', 'httpcore', 'httpx']

for handler in logger.handlers:
    handler.addFilter(ModuleFilter(banned_debug_modules))
