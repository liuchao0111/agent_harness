# 从config模块导入配置常量
# import json
# 定义函数 用于持久化较大的输出内容
import json
import time

from config import (
    DEFAULT_MAX_TOKENS,
    KEEP_RECENT,
    MAX_BYTES,
    MAX_MESSAGES,
    MODEL_ID,
    PERSIST_THRESHOLD,
    TEXT_ENCODING,
    TOOL_RESULTS_DIR,
    TRANSCRIPT_DIR,
    client,
)


def size(text: str) -> int:
    """
    计算字符串经过 UTF-8 编码后的字节数。

    例如：
    - "abc" 占 3 字节
    - "你好" 通常占 6 字节
    """
    return len(text.encode(TEXT_ENCODING))


def truncate(text: str, max_bytes: int) -> str:
    """
    将字符串截断到指定的 UTF-8 字节数以内。

    errors="ignore" 用于避免截断位置刚好落在一个中文字符中间，
    从而引发 UnicodeDecodeError。
    """
    data = text.encode(TEXT_ENCODING)
    return data[:max_bytes].decode(TEXT_ENCODING, errors="ignore")


def save_output(tool_call_id: str, output: str):
    """
    将完整的工具输出保存到文件。

    文件名使用 tool_call_id，保证不同工具调用使用不同文件。
    如果文件已经存在，则不重复写入，避免用预览内容覆盖原始完整输出。

    返回：
        完整输出文件的 Path 路径对象。
    """
    TOOL_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = TOOL_RESULTS_DIR / f"{tool_call_id}.txt"
    # 避免第二次处理时覆盖原始完整输出
    if not path.exists():
        path.write_text(output, encoding=TEXT_ENCODING)
    return path


def persist_with_preview(tool_call_id: str, output: str) -> str:
    """
    将完整工具输出保存到文件，并生成带预览的简略消息。

    最终返回内容包含：
    1. 完整输出的文件路径；
    2. 不超过 PERSIST_THRESHOLD 的部分预览。

    为了保证返回结果整体不超过阈值，需要先扣除标签和路径占用的字节。
    """
    path = save_output(tool_call_id, output)
    prefix = f"<persisted-output>\n完整输出：{path}\n预览：\n"
    suffix = "\n</persisted-output>"
    # 扣除路径和标签占用的字节，剩余空间用于预览
    preview_size = max(
        0,
        PERSIST_THRESHOLD - size(prefix + suffix),
    )
    preview = truncate(output, preview_size)
    return f"{prefix}{preview}{suffix}"


def persist_path_only(tool_call_id: str, output: str) -> str:
    """
    将完整工具输出保存到文件，但不保留内容预览。

    当所有 Tool 消息的总大小超过 MAX_BYTES 时，
    使用这种形式进一步压缩消息，只向模型提供文件路径。
    """
    path = save_output(tool_call_id, output)
    return f"<persisted-output>完整输出：{path}</persisted-output>"


def tool_result_budget(
    messages: list,
    max_bytes: int = MAX_BYTES,
) -> list:
    """
    控制消息历史中所有 Tool 输出的总体积。

    处理分为两个阶段：

    第一阶段：
        单条 Tool 输出超过 PERSIST_THRESHOLD 时，
        将完整内容保存到文件，消息中只留下路径和部分预览。

    第二阶段：
        如果处理后所有 Tool 消息总和仍然超过 max_bytes，
        则按照消息大小从大到小进一步压缩，
        去掉预览，只保留完整输出的文件路径。

    参数：
        messages：完整的对话消息列表。
        max_bytes：所有 Tool 消息允许占用的最大字节数。

    返回：
        处理后的原消息列表。
    """

    indices = [
        index for index, message in enumerate(messages) if message.get("role") == "tool"
    ]

    # 第一阶段：单条超过 2K，落盘并保留预览
    for index in indices:
        message = messages[index]
        content = str(message.get("content", ""))

        # 已经处理过，不再重复处理
        if content.startswith("<persisted-output>"):
            continue

        if size(content) > PERSIST_THRESHOLD:
            tool_call_id = message.get(
                "tool_call_id",
                f"unknown-{index}",
            )
            message["content"] = persist_with_preview(
                tool_call_id,
                content,
            )

    # 计算处理后的总字节数
    total = sum(size(str(messages[index].get("content", ""))) for index in indices)

    if total <= max_bytes:
        return messages

    # 第二阶段：总量仍然超限，优先压缩最大的消息
    ranked = sorted(
        indices,
        key=lambda index: size(str(messages[index].get("content", ""))),
        reverse=True,
    )

    for index in ranked:
        if total <= max_bytes:
            break

        message = messages[index]
        old_content = str(message.get("content", ""))
        old_size = size(old_content)

        tool_call_id = message.get(
            "tool_call_id",
            f"unknown-{index}",
        )

        # 不再保留预览，只留下完整输出的文件路径
        new_content = persist_path_only(
            tool_call_id,
            old_content,
        )
        new_size = size(new_content)

        # 新内容确实更小时才替换
        if new_size < old_size:
            message["content"] = new_content
            total -= old_size - new_size

    return messages


# 修复消息链 确保每个assistant的tool_call都能收到tool响应 同时移除孤立的tool消息
def repair_messages_chain(messages: list) -> list:
    """消息源变成了repaired 列表"""
    # 补全缺失的tool响应 移除孤立的tool消息
    """补全缺失的 tool 响应，移除孤立的 tool 消息。"""
    # 如果消息列表为空
    if not messages:
        return messages

    # 初始化用于保存修复后的消息列表
    repaired: list[dict] = []
    # 记录需要等待tool响应的tool_call集合
    # { callIdA , callIdB }
    pending_ids: set[str] = set()

    # 内部函数: 将当前等待的tool_call用reason伪造tool消息并清空待完成集合
    def flush_pending(reason: str):
        # 声明要修改外围作用域的pending_ids
        nonlocal pending_ids
        # 遍历所有等待待补全的tool_call_id 添加伪造tool响应
        for tool_call_id in pending_ids:
            repaired.append(
                {"role": "tool", "tool_call_id": tool_call_id, "content": reason}
            )
        # 清空等待集合
        pending_ids = set()

    # 遍历所有消息
    for msg in messages:
        # 获取当前角色role
        role = msg.get("role")

        # 如果是assistant角色的消息
        #  {
        #     "role": "assistant",
        #     "tool_calls": [
        #         {"id": "call_A"},
        # 。       {"id": "call_B"},
        #     ],
        # }
        #  第一次执行flush_pending 为空 空集合不用管
        #  assistant(call_A tool_calls)
        #  assistant(下一条)

        # assistant(call_A)
        # tool(call_A, "缺失")
        # assistant(下一条)
        if role == "assistant":
            # 为之前等待的tool_call_id补全缺失的工具响应
            flush_pending("[工具响应缺失，已自动补全]")
            # 添加当前的assistant消息到结果列表
            repaired.append(msg)
            # 获取辅助消息中的tool_call字段 (可能没有)
            tool_calls = msg.get("tool_calls") or []
            # 提取本assistant消息关联的所有tool调用id
            pending_ids = {
                tc.get("id")
                for tc in tool_calls
                if isinstance(tc, dict) and tc.get("id")
            }
            # 进入下一个消息
            continue
        # 如果是tool消息
        """" r如何去除孤立tool 如果pending_ids 里面没有 对应call_id 就不会添加到repaired 消息列表中去 """
        if role == "tool":
            # 获取当前tool消息中的tool_call_id
            tool_call_id = msg.get("tool_call_id")
            # 如果tool_call_id有效 且在待补全集合中
            if tool_call_id and tool_call_id in pending_ids:
                # 添加此tool消息到修复后的结果
                repaired.append(msg)
                # 标记次id已完成
                pending_ids.discard(tool_call_id)
            # 进入下一个消息
            continue
        # 除assistant与tool外 通常为user或system 补全所有pending tool响应
        # assistant(call_A)
        # user

        # 修成：
        # assistant(call_A)
        # tool(call_A, "缺失")
        # user
        flush_pending("[工具响应缺失，已自动补全]")
        # 添加当前消息到结果
        repaired.append(msg)
    # 循环结束后，最后再补全一次所有仍待补全的tool响应
    # assistant(call_A)
    # 消息列表结束
    # 修成：
    # assistant(call_A)
    # tool(call_A, "缺失")
    flush_pending("[工具响应缺失，已自动补全]")
    # 返回修复后的消息链
    return repaired


# 裁剪消息列表至最大条数 并插入消息说明 再交由repair_message_chain处理
def snip_compact(messages: list, max_messages: int = MAX_MESSAGES) -> list:
    # 如果消息总数未超过限制 直接返回
    if len(messages) <= MAX_MESSAGES:
        return messages
    # 指定头部和尾部分别保留的消息条数
    keep_head, keep_tail = 3, max_messages - 4
    # 计算被裁减(省略的消息条数) 本身还算一条
    snipped = len(messages) - keep_head - keep_tail
    # 构建裁剪后的消息列表 头 + 说明 + 尾
    compacted = (
        messages[:keep_head]
        + [{"role": "user", "content": f"[已裁剪 {snipped} 条消息]"}]
        + messages[-keep_tail:]
    )
    # 修复裁剪后的消息链
    return repair_messages_chain(compacted)


# 定义一个函数 用于收集所有role为"tole"的消息及其索引
def collector_tool_messages(messages: list) -> list:
    # 遍历消息列表 筛选出role为"tool"的消息 并返回索引和消息的元祖列表
    return [(i, m) for i, m in enumerate(messages) if m.get("role") == "tool"]


# 定义一个函数 用于对较早的工具进行内容压缩
def micro_compact(messages: list) -> list:
    # 收集所有tool类型的消息及其索引
    tool_msgs = collector_tool_messages(messages)
    # 如果tool消息不超过设定的保留数 则直接返回原消息列表
    if len(tool_msgs) <= KEEP_RECENT:
        return messages
    # 遍历除最近保留的tool消息以外的其他tool消息
    for _i, msg in tool_msgs[:-KEEP_RECENT]:
        # 获取tool消息的内容字段 并确保为字符串类型
        content = msg.get("content", "")
        # 如果内容长度超过120个字符 则进行内容压缩
        if len(content) > 120:
            # 将内容转换为压缩提示心
            msg["content"] = "[较早的工具结果已压缩。需要时请重新运行。]"
    # 返回消息列表 已就地修改
    return messages


# 定义函数estimate_size 用于计算消息列表的字符长度
def estimate_size(messages: list) -> int:
    # 将消息列表转为字符串后取长度作为大小估算
    return len(str(messages))


# 定义函数 write_transcript 用于将消息写入jsonl文件
def write_transcript(messages: list):
    # 确保转录文件夹存在 不存在则创建
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    # 拼接生成转录文件的路径(以时间戳命名)
    path = TRANSCRIPT_DIR / f"transcript_{int(time.time())}.jsonl"
    # 以 utf-8 编码打开文件 准备写入
    with path.open("w", encoding=TEXT_ENCODING) as f:
        # 遍历每条消息
        for msg in messages:
            # 将每条消息转为json字符串并写入文件 每条一行
            f.write(json.dumps(msg, default=str, ensure_ascii=False) + "\n")
    return path


# 定义 summarize_history函数 用于总结历史对话
def summarize_history(messages: list) -> str:
    # 将消息列表转换为json字符串 并裁剪至最多8万字符
    conversation = json.dumps(messages, default=str, ensure_ascii=False)[:8000]
    # 构造汇总用的prompt 要求对对话进行总结
    prompt = (
        "总结以下编程 Agent 对话，以便继续工作。\n"
        "保留: 1.当前目标 2.关键发现/决策 3. 读/改过的文件"
        "4. 剩余工作 5.用户约束。\n简介但具体。 \n\n" + conversation
    )

    # 调用大模型生成摘要
    response = client.chat.completions.create(
        model=MODEL_ID,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1000,
    )
    # 返回摘要文本 去除首尾空白 如为空则返回'(空摘要)'
    return (response.choices[0].message.content or "").strip() or "(空摘要)"


# 定义compact_history 函数 对历史消息进行压缩
def compact_history(messages: list) -> list:
    # 写入转录文件并保存路径
    transcript_path = write_transcript(messages)
    # 打印转录保存的提示
    print(f"[转录已保存: {transcript_path}]")
    # 对 历史消息进行摘要压缩
    recent = messages[-5:]
    older = messages[:-5]

    summary = summarize_history(older)

    return [
        {
            "role": "user",
            "content": f"[历史摘要]\n\n{summary}",
        },
        *recent,
    ]


# reactive_compact 保留最后 5 条：
# 为了让模型拥有准确的近期上下文，弥补摘要的信息损失。

# reactive_compact 内部修复：
# 因为 messages[-5:] 可能从 Tool 调用块中间切开。

# agent.py 最后再次修复：
# 为了保证无论走过哪种压缩路径，发送给模型前的消息链都合法


# 定义一个对历史消息进行响应式压缩的函数
def reactive_compact(messages: list) -> list:
    transcript_path = write_transcript(messages)
    summary = summarize_history(messages)

    # 紧急压缩时限制摘要长度
    summary = summary[:4000]

    return [
        {
            "role": "user",
            "content": (f"[响应式压缩]\n完整历史：{transcript_path}\n\n{summary}"),
        }
    ]
