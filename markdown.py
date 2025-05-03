import uuid
import datetime
from models import Oops
import os
import re

def save_markdown(oops: Oops) -> str:
    """
    将生成的内容保存为 Markdown 文件，修复常见的 Markdown 格式问题
    
    Args:
        oops: 生成的内容
        image_path: 图片路径
    
    Returns:
        保存的文件路径
    """
    os.makedirs("data/markdown", exist_ok=True)
    
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    
    # 获取图片文件名（不含路径和扩展名）作为标识符
    image_id = str(uuid.uuid4())[:8]
    
    # 如果是problem类型的标签，获取科目
    subject = ""
    if hasattr(oops.tags, "subject"):
        subject = oops.tags.subject
    
    # 创建文件名
    filename = f"{today}_{subject}_{image_id}.md"
    filepath = os.path.join("data/markdown", filename)
    
    problem = oops.problem
    
    answer = oops.answer
    # 替换逗号后的空格
    answer = re.sub(r',\s*', ', ', answer)
    # 确保每行结尾没有多余空格
    answer = '\n'.join(line.rstrip() for line in answer.split('\n'))
    # 替换制表符为空格
    answer = answer.replace('\t', '    ')
    
    # 修正分析部分
    analysis = oops.analysis
    analysis = '\n'.join(line.rstrip() for line in analysis.split('\n'))
    analysis = analysis.replace('\t', '    ')
    
    # 将内容写入文件
    with open(filepath, 'w', encoding='utf-8') as f:
        # 使用 ## 而不是 # 作为顶级标题，避免多个 H1 标题问题
        f.write(f"## 题目\n\n{problem}\n\n")
        f.write(f"## 正确答案\n\n{answer}\n\n")
        if analysis != "无":
            f.write(f"## 错因分析\n\n{analysis}\n\n")
        
        # 写入标签信息
        f.write("## 标签\n\n")
        
        if hasattr(oops.tags, "subject"):
            # 题目标签
            f.write("### 题目标签\n\n")
            f.write(f"* **科目:** {oops.tags.subject}\n")
            f.write(f"* **题型:** {oops.tags.question_type}\n")
            f.write(f"* **难度:** {oops.tags.difficulty}\n")
            f.write("* **知识点:** ")
            for i, kp in enumerate(oops.tags.knowledge_point):
                if i > 0:
                    f.write(", ")
                f.write(kp)
            f.write("\n")
        else:
            # 解答标签
            f.write("### 解答标签\n\n")
            f.write(f"* **作答状态:** {oops.tags.answer_status}\n")
            f.write(f"* **错因类型:** {oops.tags.error_type}\n")
            f.write(f"* **订正状态:** {oops.tags.correction_status}\n")
    
    return filepath