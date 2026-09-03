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


def safe_path(p: str, cwd: Path | None = None) -> Path:
    base = cwd or WORKDIR
    # 通过将WORKIDIR与p链接,并调用resolve方法，获得绝对路径对象
    path = (base / p).resolve()
    # 判断path路径是否在WORKDIR工作区内 如果不是则抛出异常
    if not path.is_relative_to(base.resolve()):
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


# 定义一个函数parse_frontmatter函数 参数为text 返回一个元祖(字典 字符串)
def parse_frontmatter(text: str) -> tuple[dict, str]:
    # 如果text不是以 '---' 开头 则直接返回空字典和原始文本
    if not text.startswith("---"):
        return {}, text
    # 用 '---' 分割文本 最多分割2次 得到3段内容
    parts = text.split("---", 2)
    # 如果分割出来的部分不足3个，说明无有效frontmatter，返回空字典和原始文本
    if len(parts) < 3:
        return {}, text
    # 新建一个空字典 用于存储frontmatter的键值对
    meta = {}
    # 遍历frontmatter内容区域的每一行 去首尾空白  按换行拆成列表
    for line in parts[1].strip().splitlines():
        # 如果该行包含冒号 认为是key:value格式
        if ":" in line:
            # 以冒号分割该行成键和值(只分一次)
            k, v = line.split(":", 1)
            # 去掉键和值的两端空白 并将值两端的引号去除 存入了字典
            meta[k.strip()] = v.strip().strip('"').strip("'")

    # 返回已解析好的meta字典和去除空白后的正文内容
    return meta, parts[2].strip()


# 定义一个llm_text函数 接收response对象 返回字符串类型
def llm_text(response) -> str:
    # 获取 response的第一个choice的message的content字段 如果为空则用'',去除首尾空白后返回
    return (response.choices[0].message.content or "").strip()


# 定义一个message_text函数 接收一个字典类型的msg参数 返回字符串
def message_text(msg: dict) -> str:
    # 从msg字典中获取'content'字段 若没有则默认为空字符串
    content = msg.get("content", "")
    # 如果content是字符串类型 则直接返回
    if isinstance(content, str):
        return content
    # 否则将content转换为字符串类型返回
    return str(content)
