# 倒入操作系统相关的模块
import os
from pathlib import Path

# 导入dotenv 模块来加载环境变量
from dotenv import load_dotenv

# 导入OpenAI官方python库
from openai import OpenAI

# 加载.env中的环境变量 override=True表示覆盖已有环境变量
load_dotenv(override=True)

# 设置工作目录为当前目录
WORKDIR = Path.cwd()

# Change Code Page 设置命令行编码为UTF-8 UTF-8对应的代码页编号是65001 ，GBK对应的代码编号是 936
# os.system("chcp 65001")

# 设置文本编码为UTF-8
TEXT_ENCODING = "utf-8"

# 定义默认最大的Token数
DEFAULT_MAX_TOKENS = 8000
# 从环境变量中获取主要模型名称
MODEL_ID = os.environ["MODEL_ID"]
# 创建OpenAI客户端对象 使用环境变量中的API密钥
client = OpenAI(
    api_key=os.environ["OPENAI_API_KEY"], base_url=os.environ["OPENAI_BASE_URL"]
)

# 设置技能目录为工作目录下的skills目录
SKILLS_DIR = WORKDIR / "skills"

# 设置持久化阈值为1000
PERSIST_THRESHOLD = 2000

# 设置最大字节数为100000
MAX_BYTES = 10000

# 设置工具结构目录为工作目录下的 .task_outputs / tool-results 目录
TOOL_RESULTS_DIR = WORKDIR / ".task_outputs" / "tool-results"

# 设置裁剪消息条数最大条数
MAX_MESSAGES = 50

# 设置保留最近3条tool消息
KEEP_RECENT = 3

# 设置上下文限制为100000
CONTEXT_LIMIT = 100000

# 设置转录目录为工作目录下的 .transcripts目录
TRANSCRIPT_DIR = WORKDIR / ".transcript"
