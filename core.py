# TODO: 修改导入方式，以优化实例命名
from models import OopsResponse, Request, Oops
from markdown import save_markdown
from generate import Generate # TODO: 模块改名，防混淆
from telegram_bot import Bot
from config import Env
from save import MongoSaver

from datetime import datetime
import asyncio
import os


class OopsNote:
    def __init__(self):
        """
        初始化
        创建相关模块实例

        """
        # TODO: 配置化文件创建
        os.makedirs("./data/telegram_bot", exist_ok=True)
        os.makedirs("./data/markdown", exist_ok=True)
        
        self.env = Env()
        
        self.queue: asyncio.Queue[Request] = asyncio.Queue()        

        self.generater = Generate(mode=self.env.api_mode, api_key=self.env.api_key, model=self.env.model)

        # self.saver = MongoSaver(mongo_uri=self.env.mongo_uri, database_name=self.env.database_name, collection_name=self.env.collection_name)
        self.saver = MongoSaver()

        self.bot = Bot(token=self.env.telegram_token, Queue=self.queue)


    async def deal_request(self):
        """
        处理请求，分析数据并生成内容
        """
        while True:
            data = await self.queue.get()
            try: # 添加 try 块来包裹请求处理逻辑
                if data is None: # 停止信号处理
                    print("收到停止信号， deal_request 退出。")
                    break # 退出循环

                print(f"从队列中获取到请求， Prompt: {data.prompt}\n图片已保存到 {data.image_path}")
                print("-" * 40)

                # --- 开始处理单个请求 ---
                try:
                    # 调用 AI 生成
                    wrong: OopsResponse = self.generater.generate(data) # 修正：调用 generate 而不是 gemerate
                    print(f"生成的内容：\n{wrong.problem}")

                    # 构建 Oops 对象 (需要包含 image_path)
                    oops_to_save = Oops(
                        problem=wrong.problem,
                        answer=wrong.answer,
                        analysis=wrong.analysis,
                        tags=wrong.tags,
                        image_path=data.image_path # 从原始请求中获取 image_path
                    )

                    # 保存到数据库
                    self.saver.save_oops(oops_to_save)
                    print(f"请求处理完毕并成功保存。")

                except Exception as e:
                    # 捕获处理单个请求时发生的错误
                    print(f"处理请求 (Prompt: {data.prompt}) 时发生错误: {e}")
                    # 这里可以添加更详细的错误日志记录
                    # 即使出错，循环也会继续处理下一个请求

                # --- 单个请求处理结束 ---

            finally:
                # 确保无论成功、失败还是收到 None，都调用 task_done
                if data is not None: # 只有在处理实际数据时才标记完成
                     print("-" * 40) # 分隔符
                self.queue.task_done()


    async def launch(self):
        """
        启动主程序，创建任务并运行
        """
        task_bot = asyncio.create_task(self.bot.run())
        # 不再传递 self.queue 给 deal_request
        task_deal = asyncio.create_task(self.deal_request()) 

        # 等待两个任务完成（或者直到其中一个出错）
        # 如果 bot.run() 内部的 asyncio.Future() 被取消（例如 Ctrl+C），
        # gather 会抛出 CancelledError，然后 finally 块会执行
        # TODO: 优化异常处理
        try:
            await asyncio.gather(task_bot, task_deal)
        except asyncio.CancelledError:
            print("主任务被取消，开始清理...")
        finally:
            self.saver.close()
            # 可选：发送停止信号给 deal_request，如果它还在运行
            await self.queue.put(None) 
            # 等待 deal_request 处理完剩余任务并退出
            await self.queue.join() 
            print("所有任务已处理完毕。")