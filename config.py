# 倒入操作系统相关的模块
import os 
# 导入Path对象用于处理文件路径
# from pathlib import Path

# 导入dotenv 模块来加载环境变量
from dotenv import load_dotenv

#导入OpenAI官方python库
from openai import OpenAI
 
 #加载.env中的环境变量 override=True表示覆盖已有环境变量
load_dotenv(override=True)

# 定义默认最大的Token数
DEFAULT_MAX_TOKENS = 8000
#从环境变量中获取主要模型名称
MODEL_ID = os.environ['MODEL_ID']
#创建OpenAI客户端对象 使用环境变量中的API密钥
client = OpenAI(
    api_key=os.environ['OPENAI_API_KEY'],
    base_url= os.environ['OPENAI_BASE_URL']
)