"""
队列持久化模块
提供队列状态的保存和加载功能
"""
import os
import pickle
from abc import ABC, abstractmethod
from typing import List, Any
import logging
import asyncio

logger = logging.getLogger(__name__)

class QueuePersistence(ABC):
    """
    队列持久化抽象基类
    定义了保存和加载队列数据的接口
    """
    @abstractmethod
    def save(self, items: List[Any]) -> bool:
        """保存队列项到持久化存储"""
        pass
    
    @abstractmethod
    def load(self) -> List[Any]:
        """从持久化存储加载队列项"""
        pass


class PickleFileQueuePersistence(QueuePersistence):
    """
    使用Pickle文件实现队列持久化
    将队列数据序列化到文件系统
    """
    def __init__(self, file_path: str):
        """
        初始化
        
        Args:
            file_path: 存储队列数据的文件路径
        """
        self.file_path = file_path
        # 确保父目录存在
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    def save(self, items: List[Any]) -> bool:
        """
        将队列项保存到Pickle文件
        
        Args:
            items: 要保存的队列项列表
        
        Returns:
            bool: 保存是否成功
        """
        if not items:
            logger.info("队列为空，无需保存状态。")
            return True
            
        try:
            with open(self.file_path, 'wb') as f:
                pickle.dump(items, f)
            logger.info(f"成功将 {len(items)} 个未处理的任务保存到 {self.file_path}。")
            return True
        except (pickle.PicklingError, IOError) as e:
            logger.error(f"保存队列状态到 {self.file_path} 失败: {e}")
            return False
        except Exception as e:
            logger.error(f"保存队列时发生未知错误: {e}")
            return False
    
    def load(self) -> List[Any]:
        """
        从Pickle文件加载队列项
        
        Returns:
            List[Any]: 加载的队列项列表，如果加载失败则返回空列表
        """
        if not os.path.exists(self.file_path):
            return []
            
        try:
            with open(self.file_path, 'rb') as f:
                items = pickle.load(f)
            logger.info(f"成功从 {self.file_path} 加载了 {len(items)} 个未处理的任务。")
            
            # 加载成功后删除文件，避免重复加载
            os.remove(self.file_path)
            logger.info(f"已删除队列状态文件: {self.file_path}")
            
            return items
        except (FileNotFoundError, pickle.UnpicklingError, EOFError, TypeError) as e:
            logger.error(f"加载队列状态文件 {self.file_path} 失败: {e}。将启动空队列。")
            return []
        except Exception as e:
            logger.error(f"加载队列时发生未知错误: {e}。将启动空队列。")
            return []

    def load_queue(self, queue: asyncio.Queue):
        """
        从持久化存储加载上次未完成的队列任务到指定的 asyncio.Queue
        
        Args:
            queue: 要加载任务的目标队列
        """
        items = self.load() # 调用自身的 load 方法获取数据
        for item in items:
            queue.put_nowait(item)
        if items:
             logger.info(f"已将 {len(items)} 个任务加载到内存队列。")
        else:
             logger.info("没有从持久化存储中加载任务。")


    def save_queue(self, queue: asyncio.Queue):
        """
        将当前 asyncio.Queue 中未处理的任务保存到持久化存储
        
        Args:
            queue: 要保存任务的源队列
        """
        items_to_save = []
        while not queue.empty():
            try:
                # 使用 get_nowait 避免阻塞
                item = queue.get_nowait()
                # 确保 None 信号不被保存 (虽然我们主要靠取消，但以防万一)
                if item is not None:
                    items_to_save.append(item)
                # 标记任务完成，即使我们没有处理它，因为我们要保存它
                queue.task_done()
            except asyncio.QueueEmpty:
                break # 队列已空
            except Exception as e:
                logger.error(f"从队列取出任务准备保存时出错: {e}")
                # 出错时也标记完成，避免卡住 join (虽然我们不用 join 了)
                try:
                    queue.task_done()
                except ValueError: # 如果任务已被标记完成
                    pass
        
        # 调用自身的 save 方法保存数据
        self.save(items_to_save)