# 从 pathlib 库中导入 Path 类，用于管理和操作文件路径
from pathlib import Path

# 从config模块中导入WORKDIR变,表示工作目录路径
from config import WORKDIR


# 定义一个函数assistant_message_dict 参数为message , 返回一个字典
def assistant_message_dict(message) -> dict:
    # 使用model_dump方法转换message对象为字典 排除值为None的项
    data = message.model_dump(exclude_none=True)
    # 将字典中的'role'设置为'assistant'
    data["role"] = "assistant"
    # 返回处理后的字典
    return data


# 定义一个函数 decode_subprocess_output 参数为data(字节类型或None) 返回字符串类型
def decode_subprocess_output(data: bytes | None) -> str:
    # 如果data为None或者为空子节 则返回空字符串
    if not data:
        return ""
    # 依次尝试三种编码方式进行编码
    for encoding in ("utf-8", "gbk", "cp936"):
        try:
            # 使用当前编码方式尝试解码，成功则返回结果
            return data.decode(encoding)
        # 如果解码时出现UnicodeDecodeError，则继续尝试下一个编码
        except UnicodeDecodeError:
            continue
    # 如果以上编码都无法解码，则使用utf-8编码并使用replace策略处理错误，并返回结果
    return data.decode("utf-8", errors="replace")


def safe_path(p: str) -> Path:
    # 通过将WORKIDIR与p链接,并调用resolve方法，获得绝对路径对象
    path = (WORKDIR / p).resolve()
    # 判断path路径是否在WORKDIR工作区内 如果不是则抛出异常
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"路径超出工作区 {p}")
    # 返回最终安全生成的最终路径对象
    return path


# 定义一个extract_text函数 参数为content 返回字符串类型
def extract_text(content) -> str:
    # 如果content为None 返回空字符串
    if content is None:
        return ""
    # 如果content是字符串类型 直接返回
    if isinstance(content, str):
        return content
    # 否则 将content转换为字符串再返回
    return str(content)
