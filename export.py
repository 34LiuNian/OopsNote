import os
import datetime
import uuid
from models import Oops
from save import MongoSaver # <--- 导入数据库操作类
from config import Env      # <--- 导入配置加载类
from logger import logging  # <--- 导入日志记录器

logger = logging.getLogger(__name__)

# --- Markdown 模板 ---
# 每道题目的模板
MARKDOWN_ITEM_TEMPLATE = """
### 题目

{problem}

### 正确答案

{answer}

### 错因分析

{analysis}

---
"""

# 文档头部模板
MARKDOWN_HEADER = """# 错题汇总

> 导出时间: {timestamp}
> 总题目数: {total_count}

---
"""

def format_oops_to_markdown(oops: Oops) -> str:
    """将单个 Oops 对象格式化为 Markdown 字符串"""
    # 处理图片部分
    return MARKDOWN_ITEM_TEMPLATE.format(
        problem=oops.problem or "无",
        answer=oops.answer or "无",
        analysis=oops.analysis or "无",
    )

def export_all_to_single_markdown(output_file="exports/all_oops_records.md"):
    """从数据库导出所有 Oops 记录到一个单独的 Markdown 文件"""
    logger.info("开始从数据库导出所有错题记录到单个Markdown文件...")
    env = Env()
    exported_count = 0
    failed_count = 0
    all_markdown_content = []

    # 检查必要的数据库配置
    mongo_uri = env.mongo_uri
    database_name = env.database_name or "OopsDB"
    
    if not mongo_uri:
        logger.error("未配置MongoDB连接URI，请检查.env文件中的MONGO_URI设置。")
        return

    logger.info(f"将连接到数据库: {database_name}")

    try:
        # 确保输出目录存在
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        # 使用 with 语句确保连接关闭
        with MongoSaver(mongo_uri=mongo_uri, database_name=database_name) as saver:
            # 修正：Collection 对象不支持布尔值测试，必须用 is None 判断
            if saver.client is None or saver.collection is None:
                logger.error("未能成功连接到数据库，导出中止。")
                return

            # 查询所有记录并按照科目排序
            all_records = list(saver.collection.find({}))
            logger.info(f"从数据库中获取了 {len(all_records)} 条记录。")
            
            # 如果没有记录，生成空的Markdown
            if not all_records:
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                header = MARKDOWN_HEADER.format(timestamp=timestamp, total_count=0)
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(header)
                    f.write("\n\n*没有找到任何错题记录，数据库为空。*")
                logger.info(f"导出完成，但数据库中没有记录。Markdown文件已保存到: {output_file}")
                return

            # 添加文档头部
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            header = MARKDOWN_HEADER.format(timestamp=timestamp, total_count=len(all_records))
            all_markdown_content.append(header)

            # 处理每条记录
            for record in all_records:
                try:
                    # 使用 Pydantic 模型验证数据结构
                    oops_instance = Oops.model_validate(record)
                    record_id = str(record.get('_id', '未知ID'))
                    
                    # 格式化为Markdown
                    markdown_content = format_oops_to_markdown(oops_instance)
                    all_markdown_content.append(markdown_content)
                    
                    exported_count += 1
                    logger.debug(f"成功处理记录 {record_id}")

                except Exception as e:
                    failed_count += 1
                    record_id_str = str(record.get('_id', '未知ID'))
                    logger.error(f"处理记录 {record_id_str} 时出错: {e}", exc_info=True)

            # 写入单一Markdown文件
            with open(output_file, "w", encoding="utf-8") as f:
                f.write("\n".join(all_markdown_content))

            logger.info(f"导出完成！成功处理 {exported_count} 条记录，失败 {failed_count} 条。")
            logger.info(f"Markdown文件已保存到: {output_file}")

    except Exception as e:
        logger.error(f"导出过程中发生严重错误: {e}", exc_info=True)

if __name__ == "__main__":
    # 当直接运行这个脚本时，执行导出操作
    export_all_to_single_markdown()
    # 你也可以指定不同的输出文件，例如：
    # export_all_to_single_markdown(output_file="exports/错题汇总.md")