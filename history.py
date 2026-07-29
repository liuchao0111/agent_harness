# 从config模块导入配置常量
from config import MAX_BYTES, PERSIST_THRESHOLD, TEXT_ENCODING, TOOL_RESULTS_DIR

# import json


# 定义函数 用于持久化较大的输出内容
def persist_large_output(tool_call_id: str, output: str) -> str:
    # 如果输出内容未超过阈值 则直接返回原内容
    if len(output) <= PERSIST_THRESHOLD:
        return output
    # 创建工具输出目录(如果不存在 则直接创建)
    TOOL_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    # 构建持久化内容的文件路径
    path = TOOL_RESULTS_DIR / f"{tool_call_id}.txt"
    # 如果文件还不存在
    if not path.exists():
        path.write_text(output, encoding=TEXT_ENCODING)
    # 返回包含完整输出文件路径和部分预览内容的字符串
    return f"<pesisted-output>\n完整输出 : {path}\n预览:\n{output[:2000]}\n</persisted-output>"


# 定义函数 用于管理工具类型消息的总内容体积预算
def tool_result_budget(messages: list, max_bytes: int = MAX_BYTES) -> list:
    # 获取所有 role 为 tool的消息 下表列表
    indices = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
    # 如果没有 tool 类型消息 则直接返回原消息列表
    if not indices:
        return messages
    # 计算所有 tool 消息内容的总字节数
    total = sum(len(messages[i].get("content", "") for i in indices))
    # 如果总字节数未超出最大限制 直接返回原消息列表
    if total <= max_bytes:
        return messages
    # 按消息内容长度从大到小对 tool 消息下标进行排序
    ranked = sorted(
        indices, key=lambda i: len(str(messages[i].get("content", ""))), reverse=True
    )
    # 遍历排序后的 tool消息下标
    for i in ranked:
        # 如果总字节数已小于等于最大限制 则停止处理
        if total <= max_bytes:
            break
        # 获取当前消息
        msg = messages[i]
        # 获取消息内容 转为字符串
        content = str(msg.get("content", ""))
        # 如内容长度未超过持久化阈值 跳过
        if len(content) <= PERSIST_THRESHOLD:
            continue
        # 获取工具调用的 id 默认为unknown
        tid = msg.get("tool_call_id", "unknown")
        # 将较大的输出内容持久化 并替换为简略信息
        msg["content"] = persist_large_output(tid, content)
        # 重新计算所有 tool 消息内容的总字节数
        total = sum(len(str(messages[i].get("content", ""))) for i in indices)
    # 返回处理之后的消息列表
    return messages
