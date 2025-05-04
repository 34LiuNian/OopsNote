# OopsNote 📝

## 描述 🧐

这是一个使用 Python 编写的项目，致力于让错题整理变得轻松愉快！✨

## 功能 ✨

* 🤖 通过 Telegram 机器人进行交互 (`telegram_bot.py`)
* 🧠 利用 AI 分析图片中的题目并生成解答 (`generate.py`)
* 💾 将整理好的错题保存到 MongoDB (`save.py`)
* 🔄 通过队列持久化确保任务不丢失 (`queue_persistence.py`)
* ⚙️ 核心业务逻辑编排 (`core.py`)
* 🧱 使用 Pydantic 定义清晰的数据模型 (`models.py`)
* 🔑 通过 `.env` 文件管理配置 (`config.py`)
* 📄 (可选) 导出为 Markdown 或 PDF (`export.py`, `markdown.py`)

## 安装 🛠️

1. 克隆仓库：

    ```bash
    git clone https://github.com/34LiuNian/OopsNote.git
    cd OopsNote
    ```

2. 创建并激活虚拟环境 (推荐)：

    ```bash
    # Linux/macOS
    python3 -m venv venv
    source venv/bin/activate

    # Windows
    python -m venv venv
    venv\Scripts\activate
    ```

3. 安装依赖：

    ```bash
    pip install -r requirements.txt
    ```

## 配置 ⚙️

1. **复制环境变量模板**:
    项目根目录下通常会有一个 `.env.example` 文件 (如果没有，请根据需要创建一个)。复制它并命名为 `.env`。

    ```bash
    # 如果存在 .env.example
    cp .env.example .env
    # 如果不存在，则手动创建 .env 文件
    ```

2. **编辑 `.env` 文件**: ✏️
    打开 `.env` 文件，填入你的配置信息。关键配置包括：

* `TELEGRAM_BOT_TOKEN`: 你的 Telegram 机器人令牌 🤖。
* `API_MODE`: 使用的 AI 服务 (`GEMINI` 或 `OPENAI`)。
* `GEMINI_API_KEY` / `OPENAI_API_KEY`: 对应 AI 服务的 API 密钥 🔑。
* `GEMINI_ENDPOINT` / `OPENAI_ENDPOINT`: 对应 AI 服务的接入点 URL (如果需要指定)。
* `GEMINI_MODEL` / `OPENAI_MODEL`: 使用的 AI 模型名称。
* `PROMPT_FILE`: 指向 `prompt.md` 文件的路径 (定义 AI 的角色和输出格式)。
* `MONGO_URI`: MongoDB 连接字符串 💾 (例如: `mongodb://localhost:27017`)。
* `DATABASE_NAME`: MongoDB 数据库名称 (例如: `OopsDB`)。
* `DUMP_FILE`: 队列持久化文件的路径 (例如: `data/queue.pkl`)。

    ```dotenv
    # .env 文件示例
    TELEGRAM_BOT_TOKEN="YOUR_TELEGRAM_BOT_TOKEN"

    API_MODE="GEMINI" # 或 "OPENAI"

    GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
    GEMINI_ENDPOINT="YOUR_GEMINI_ENDPOINT_IF_NEEDED" # 例如 aihubmix 的地址
    GEMINI_MODEL="gemini-pro" # 或其他模型

    # 如果使用 OPENAI
    # OPENAI_API_KEY="YOUR_OPENAI_API_KEY"
    # OPENAI_ENDPOINT="YOUR_OPENAI_ENDPOINT_IF_NEEDED"
    # OPENAI_MODEL="gpt-4-vision-preview"

    PROMPT_FILE="./prompt.md"
    MONGO_URI="mongodb://localhost:27017"
    DATABASE_NAME="OopsDB"
    DUMP_FILE="data/queue.pkl"
    ```

## 使用 ▶️

直接运行主程序：

```bash
python main.py
```

机器人启动后，你就可以在 Telegram 里给它发送带有题目的图片啦！

## 注意事项 ⚠️

* 请确保 `.env` 文件已正确配置并且包含了所有必要的密钥和路径。
* 确保 MongoDB 服务正在运行并且网络可达。
* 如果使用代理或特定的 AI 服务接入点，请确保网络连接正常。

## 贡献 ❤️

欢迎提交问题 (Issues) 和拉取请求 (Pull Requests)！让我们一起让 OopsNote 变得更好！🤝

## 许可证 📄

本项目采用 [AGPL-3.0](LICENSE) 许可证。

## 📁 项目结构 (简化)

```plaintext
.
├── 🤖 telegram_bot.py   # Telegram Bot 交互逻辑
├── 🧠 generate.py       # AI 内容生成模块
├── 💾 save.py           # MongoDB 数据保存
├── 🔄 queue_persistence.py # 队列持久化实现
├── ⚙️ core.py           # 核心业务逻辑与任务调度
├── 🧱 models.py         # Pydantic 数据模型定义
├── 🔑 config.py         # 加载 .env 配置
├── 📄 markdown.py       # (旧) Markdown 文件保存 (可能被 export.py 替代)
├── 📤 export.py         # 导出功能 (Markdown, PDF)
├── 📜 prompt.md         # AI 系统指令模板
├── 📦 requirements.txt  # Python 依赖列表
├── 🚀 main.py           # 程序主入口
├── 🧪 tests/            # 测试文件目录
│   ├── test_core.py
│   ├── test_queue_persistence.py
│   └── ...
├── 📄 .env              # 环境变量 (需自行根据 .env.example 创建)
├── 📄 .gitignore        # Git 忽略配置
├── 📄 README.md         # 就是你现在看到的这个文件
├── 📄 LICENSE           # 项目许可证
└── 📁 data/             # 数据存储目录 (自动创建)
    ├── 🖼️ telegram_bot/ # Telegram 接收的图片
    ├── 📝 markdown/     # (可选) 生成的 Markdown 文件
    └── 💾 queue.pkl      # (或 .env 中指定的其他名称) 队列持久化文件
```

---
