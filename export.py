import os
import datetime
import uuid
import pdfkit
from models import Oops

class MarkdownExporter:
    def __init__(self, output_dir="data/markdown", css_file=None):
        """
        初始化导出器
        Args:
            output_dir: Markdown 文件保存路径
            css_file: 自定义 CSS 文件路径（用于 PDF 导出）
        """
        self.output_dir = output_dir
        self.css_file = css_file
        os.makedirs(self.output_dir, exist_ok=True)

    def export_markdown(self, oops_list: list[Oops]) -> list[str]:
        """
        批量导出 Oops 对象为 Markdown 文件
        Args:
            oops_list: Oops 对象列表
        Returns:
            保存的 Markdown 文件路径列表
        """
        filepaths = []
        for oops in oops_list:
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
            if oops.image_path:
                content.append(f"![题目图片]({oops.image_path})\n")

            # 添加标签信息
            if hasattr(oops, "tags"):
                content.append("## 标签\n")
                for key, value in vars(oops.tags).items():
                    if isinstance(value, list):
                        value = ", ".join(value)
                    content.append(f"- **{key}:** {value}\n")

            # 写入文件
            with open(filepath, "w", encoding="utf-8") as f:
                f.writelines(content)

            filepaths.append(filepath)

        return filepaths

    def export_pdf(self, oops_list: list[Oops], pdf_output: str):
        """
        批量导出 Oops 对象为 PDF 文件
        Args:
            oops_list: Oops 对象列表
            pdf_output: 输出 PDF 文件路径
        """
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>错题</title>
        """

        # 添加自定义 CSS
        if self.css_file and os.path.exists(self.css_file):
            html_content += f'<link rel="stylesheet" href="{self.css_file}">\n'

        html_content += """
        </head>
        <body>
        """

        # 添加每个 Oops 的内容
        for oops in oops_list:
            html_content += f"<h1>题目</h1><p>{oops.problem}</p>\n"
            html_content += f"<h2>正确答案</h2><p>{oops.answer}</p>\n"
            html_content += f"<h2>错因分析</h2><p>{oops.analysis or '无'}</p>\n"

            # 添加图片
            if oops.image_path:
                html_content += f'<img src="{oops.image_path}" alt="题目图片" style="max-width:100%;">\n'

            # 添加标签
            if hasattr(oops, "tags"):
                html_content += "<h2>标签</h2><ul>\n"
                for key, value in vars(oops.tags).items():
                    if isinstance(value, list):
                        value = ", ".join(value)
                    html_content += f"<li><strong>{key}:</strong> {value}</li>\n"
                html_content += "</ul>\n"

        html_content += """
        </body>
        </html>
        """

        # 使用 pdfkit 导出 PDF
        pdfkit.from_string(html_content, pdf_output, options={"encoding": "utf-8"})