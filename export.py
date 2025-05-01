import os
import datetime
import uuid
from models import Oops

class MarkdownExporter:
    def __init__(self, output_dir="data/markdown"):
        """
        初始化导出器
        Args:
            output_dir: Markdown 文件保存路径
        """
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def export(self, oops: Oops, image_path: str = None, custom_sections: dict = None) -> str:
        """
        导出 Oops 对象为 Markdown 文件
        Args:
            oops: Oops 对象
            image_path: 图片路径（可选）
            custom_sections: 自定义 Markdown 部分（可选）
        Returns:
            保存的 Markdown 文件路径
        """
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        file_id = str(uuid.uuid4())[:8]
        filename = f"{today}_{file_id}.md"
        filepath = os.path.join(self.output_dir, filename)

        # 默认 Markdown 内容
        content = [
            f"# 题目\n\n{oops.problem}\n",
            f"## 正确答案\n\n{oops.answer}\n",
            f"## 错因分析\n\n{oops.analysis or '无'}\n",
        ]

        # 添加图片引用
        if image_path:
            content.append(f"![题目图片]({image_path})\n")

        # 添加标签信息
        if hasattr(oops, "tags"):
            content.append("## 标签\n")
            for key, value in vars(oops.tags).items():
                if isinstance(value, list):
                    value = ", ".join(value)
                content.append(f"- **{key}:** {value}\n")

        # 添加自定义部分
        if custom_sections:
            for section_title, section_content in custom_sections.items():
                content.append(f"## {section_title}\n\n{section_content}\n")

        # 写入文件
        with open(filepath, "w", encoding="utf-8") as f:
            f.writelines(content)

        return filepath