# OopsNote

## 描述

这是一个使用 Python 编写的项目，用于错题整理。

## 功能

* 通过 Telegram 机器人进行交互 (`telegram_bot.py`)
* 生成内容 (`generate.py`)
* 处理 Markdown (`markdown.py`)
* 保存数据 (`save.py`)
* 核心逻辑 (`core.py`)
* 数据模型 (`models.py`)
* 配置管理 (`config.py`)

## 安装

1. 克隆仓库：

    ```bash
    git clone https://github.com/34LiuNian/OopsNote.git
    cd OopsNote
    ```

2. 创建并激活虚拟环境：

    ```bash
    python -m venv venv
    source venv/bin/activate  # Linux/macOS
    venv\Scripts\activate  # Windows
    ```

3. 安装依赖：

    ```bash
    pip install -r requirements.txt
    ```

## 配置

1. 复制 `.env.example` 文件为 `.env`：

    ```bash
    cp .env.example .env
    ```

2. 编辑 `.env` 文件并填入必要的配置信息，例如：

    * `TELEGRAM_BOT_TOKEN`: 你的 Telegram 机器人令牌。
    * `ALLOWED_USER_IDS`: 允许使用机器人的 Telegram 用户 ID (逗号分隔)。
    * `API_KEY`: 你的 Gemini API 密钥。
    * [其他必要的环境变量]

## 使用

运行主程序：

```bash
python main.py
```

## 注意事项

* 确保已正确配置 `.env` 文件。

## 贡献

欢迎提交问题和拉取请求。

## 许可证

AGPL许可证

## 📁 项目结构 (简化)

```bash
.
├── core.py           # AI 生成核心逻辑
├── telegram_bot.py   # Telegram Bot 类
├── main.py           # 主程序入口
├── models.py         # Pydantic 数据模型
├── config.py         # 配置加载
├── markdown.py       # Markdown 文件保存 (如果独立)
├── requirements.txt  # 依赖列表
├── .env              # 环境变量 (需要自行创建)
├── data/             # 数据存储目录
│   ├── telegram_bot/ # Telegram 接收的图片
│   └── markdown/     # 生成的 Markdown 文件
└── README.md         # 就是这个文件
```

---
