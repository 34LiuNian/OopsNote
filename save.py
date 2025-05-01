import os
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
from models import Oops
from typing import Optional

class MongoSaver:
    """
    用于连接 MongoDB 并保存 Oops 对象的类。
    """
    def __init__(self, 
                 mongo_uri: Optional[str] = None, 
                 database_name: str = "OopsDB", 
                 collection_name: str = "oops_records"):
        """
        初始化 MongoSaver 实例。

        Args:
            mongo_uri (Optional[str]): MongoDB 连接字符串。如果为 None，则尝试从环境变量 "MONGO_URI" 获取，
                                       默认为 "mongodb://localhost:27017/"。
            database_name (str): 要使用的数据库名称。默认为 "OopsDB"。
            collection_name (str): 要使用的集合名称。默认为 "oops_records"。
        """
        self.mongo_uri = mongo_uri
        self.database_name = database_name
        self.collection_name = collection_name
        self.client: Optional[MongoClient] = None
        self.db = None
        self.collection = None
        self._connect()

    def _connect(self):
        """建立 MongoDB 连接。"""
        try:
            self.client = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=5000) # 添加超时
            # 测试连接
            self.client.admin.command('ping')
            self.db = self.client[self.database_name]
            self.collection = self.db[self.collection_name]
            print(f"成功连接到 MongoDB: {self.mongo_uri}, 数据库: {self.database_name}, 集合: {self.collection_name}")
        except ConnectionFailure:
            print(f"错误：无法连接到 MongoDB 服务器 at {self.mongo_uri}")
            self.client = None # 连接失败，重置 client
            raise ConnectionFailure(f"无法连接到 MongoDB 服务器 at {self.mongo_uri}")
        except Exception as e:
            print(f"连接 MongoDB 时发生意外错误: {e}")
            self.client = None
            raise e # 重新抛出异常

    def save_oops(self, oops_instance: Oops) -> Optional[str]:
        """
        将 Oops 对象保存到 MongoDB。

        Args:
            oops_instance (Oops): 要保存的 Oops Pydantic 对象。

        Returns:
            Optional[str]: 成功插入的文档的 _id (字符串形式)，如果失败则返回 None。
        """
        # 修改这里的判断条件
        if self.client is None or self.collection is None:
            print("错误：未建立 MongoDB 连接，无法保存。")
            return None

        try:
            # 将 Pydantic 对象转换为字典
            oops_dict = oops_instance.model_dump(mode='json') # 使用 mode='json' 确保兼容 BSON

            # print(f"\n准备写入 MongoDB 的数据 (字典格式):")
            # print(oops_dict)

            # 插入文档
            insert_result = self.collection.insert_one(oops_dict)
            inserted_id = str(insert_result.inserted_id) # 转换为字符串

            print(f"\n成功将 Oops 对象写入 MongoDB!")
            print(f"文档 ID (_id): {inserted_id}")

            return inserted_id

        except OperationFailure as e:
            print(f"错误：MongoDB 操作失败: {e.details}")
            return None
        except Exception as e:
            print(f"保存到 MongoDB 时发生意外错误: {e}")
            return None

    def _verify_write(self, inserted_id_str: str):
        """ (可选) 验证写入的数据 """
        if self.collection is None: return # 检查 collection 是否为 None
        from bson import ObjectId # 需要导入 ObjectId 来查询
        try:
            retrieved_doc = self.collection.find_one({"_id": ObjectId(inserted_id_str)})
            if retrieved_doc:
                print("\n从 MongoDB 检索刚写入的文档:")
                # 验证 Pydantic 模型是否能解析检索到的文档
                retrieved_oops = Oops.model_validate(retrieved_doc)
                print(retrieved_oops)
            else:
                print("\n错误：未能检索到刚写入的文档。")
        except ImportError:
             print("错误：需要安装 'bson' (通常随 pymongo 一起安装) 才能进行验证。")
        except Exception as e:
             print(f"验证写入时出错: {e}")

    def close(self):
        """关闭 MongoDB 连接。"""
        if self.client:
            self.client.close()
            print("\nMongoDB 连接已关闭。")
            self.client = None

    def __enter__(self):
        """支持 with 语句，返回自身实例。"""
        # 连接已在 __init__ 中建立
        if not self.client:
             self._connect() # 如果初始化失败，尝试重新连接
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """支持 with 语句，在退出时关闭连接。"""
        self.close()

# --- 示例用法 ---
if __name__ == "__main__":
    # 假设你有一个 Oops 实例 (需要从 models 导入 Tags)
    from models import Tags # 确保导入 Tags
    oops_instance_example = Oops(
        problem="求解方程 x^2 - 5x + 6 = 0",
        answer="x = 2 或 x = 3",
        analysis="因式分解 (x-2)(x-3) = 0，或者使用求根公式。",
        tags=Tags(
            problem=Tags.Problem(
                subject="数学",
                question_type="一元二次方程",
                difficulty="中等",
                knowledge_point=["因式分解", "求根公式"]
            ),
            answer=Tags.Answer(
                answer_status="正确",
                error_type="无",
                correction_status="无需订正"
            )
        ),
        image_path="/path/to/equation_image.png"
    )

    # 方法一：直接实例化和调用
    # saver = None
    # try:
    #     saver = MongoSaver() # 使用默认或环境变量配置
    #     # 或者指定参数: saver = MongoSaver(mongo_uri="mongodb://user:pass@host:port/", database_name="MyOops")
    #     if saver.client: # 检查连接是否成功
    #         inserted_id = saver.save_oops(oops_instance_example)
    #         if inserted_id:
    #             print(f"保存成功，ID: {inserted_id}")
    #         else:
    #             print("保存失败。")
    # except Exception as e:
    #      print(f"初始化或保存过程中出错: {e}")
    # finally:
    #     if saver:
    #         saver.close()

    # 方法二：使用 with 语句 (推荐，自动管理连接关闭)
    try:
        with MongoSaver() as saver:
            inserted_id = saver.save_oops(oops_instance_example)
            if inserted_id:
                print(f"使用 with 语句保存成功，ID: {inserted_id}")
                saver._verify_write(inserted_id) # 在连接关闭前验证
            else:
                print("使用 with 语句保存失败。")
    except ConnectionFailure as e:
         print(f"无法连接到数据库: {e}")
    except Exception as e:
         print(f"使用 with 语句时发生错误: {e}")
