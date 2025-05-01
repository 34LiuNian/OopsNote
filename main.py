from core import Generate
from models import OopsResponse, Request
from markdown import save_markdown
from config import Env
from telegram_bot import Bot
import asyncio
import os
from datetime import datetime

os.makedirs("./data/telegram_bot", exist_ok=True)
os.makedirs("./data/markdown", exist_ok=True)

queue: asyncio.Queue[Request] = asyncio.Queue()

env = Env()

core = Generate(api_key=env.api_key, model=env.model)

bot = Bot(token=env.telegram_token, Queue=queue)


async def deal_request(queue: asyncio.Queue):
    """
    处理请求的函数
    """
    while True:
        data = await queue.get()
        if data is None: # 停止信号处理
            print("收到停止信号，deal_request 退出。")
            queue.task_done() # 标记任务完成
            break
        print(f"从队列中获取到请求，Prompt: {data.prompt}")
        # 例如调用 core.generate
        # wrong: OopsResponse = core.generate(data)
        # save(wrong) # TODO: 处理生成的内容
        
        # 暂时只打印和保存图片
        output_filename = f"./data/markdown/output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        with open(output_filename, "wb") as f:
            f.write(data.image)
        print(f"图片已保存到 {output_filename}")
        print(f"收到的 Prompt: {data.prompt}")
        print("-" * 20)
        queue.task_done()


# 保存为 Markdown 文件
# markdown_path = save_markdown(wrong, image_path)
async def main():
    task_bot = asyncio.create_task(bot.run())
    task_deal = asyncio.create_task(deal_request(queue))
    
    # 等待两个任务完成（或者直到其中一个出错）
    # 如果 bot.run() 内部的 asyncio.Future() 被取消（例如 Ctrl+C），
    # gather 会抛出 CancelledError，然后 finally 块会执行
    try:
        await asyncio.gather(task_bot, task_deal)
    except asyncio.CancelledError:
        print("主任务被取消，开始清理...")
    finally:
        # 可选：发送停止信号给 deal_request，如果它还在运行
        await queue.put(None) 
        # 等待 deal_request 处理完剩余任务并退出
        await queue.join() 
        print("所有任务已处理完毕。")


if __name__ == "__main__":
    asyncio.run(main())
