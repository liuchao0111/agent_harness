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
