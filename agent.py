# 导入json库 用于处理json数据
import json

# 从config模块导入默认设置的最大token数和主模型
from config import CONTEXT_LIMIT, DEFAULT_MAX_TOKENS, MODEL_ID

# 从hooks模块导入trigger_hooks函数
from history import (
    compact_history,
    estimate_size,
    micro_compact,
    reactive_compact,
    repair_messages_chain,
    snip_compact,
    tool_result_budget,
)
from hooks import trigger_hooks

# 从llm模块导入call_llm函数
from llm import call_llm, is_prompt_too_long_error

# 从prompt模块导入get_system_prompt函数
from prompt import get_system_prompt

# 从tools.executor模块导入execute_tool函数
from tools.executor import execute_tool

# 从utils模块导入assistant_message_dict函数
from utils import assistant_message_dict

# 定义变量rounds_since_todo 用于记录自上次todo_write调用以来的轮数
rounds_since_todo = 0


# 定义agent_loop函数 参数是消息列表
def agent_loop(messages: list):
    # 声明全局变量rounds_since_todo
    global rounds_since_todo
    # 将最大的token数设置为默认值
    max_tokens = DEFAULT_MAX_TOKENS
    # 设置所用模型为主模型P
    model = MODEL_ID
    # 开始循环 直到return退出
    while True:
        # 获取系统提示词
        system = get_system_prompt()
        # L3:tool_result_budget 超大tool结果落盘
        messages[:] = tool_result_budget(messages)
        # L1: snip_compact - 消息 > 50 条时保留 头3 + 尾 46, 中间裁掉
        messages[:] = snip_compact(messages)
        # L2: micro_compact - 仅保留最近 3 条 tool完整内容 旧的换占位符
        messages[:] = micro_compact(messages)
        # L4: compcat_history - 超出上下文限制写 transcript -> LLM摘要 -> 替换为一条[已压缩]
        if estimate_size(messages) > CONTEXT_LIMIT:
            print("[自动压缩]")
            messages[:] = compact_history(messages)
        # 修复消息链: 补全缺失的tool响应 移除独立的 tool 消息
        # todo 为什么这个位置还要调用 移除独立tool消息的方法
        messages[:] = repair_messages_chain(messages)
        # 如果距离上次 todo 写入的论述大于等于3 且消息列表不为空
        if rounds_since_todo >= 3 and messages:
            # 在消息列表中添加一条用户提醒 提示助手更新todo列表
            messages.append(
                {
                    "role": "user",
                    "content": "<reminder>请更新你的 todo 列表。<reminder>",
                }
            )
            print("\x1b[33m> 请更新你的 todo 列表。\x1b[0m")
            # 轮数计数器rounds_since_todo 复位为 0
            rounds_since_todo = 0
        # 调用大模型获取回复
        try:
            response = call_llm(system, messages, max_tokens, model)
        except Exception as e:
            # 如果捕获到的异常提示是提示词过长的错误
            if is_prompt_too_long_error(e):
                # 对消息列表进行反应式压缩 减少长度
                messages[:] = reactive_compact(messages)
                # 跳过本次循环 进行下一次
                continue
            raise
        # 取出回复中的第一个回复
        choice = response.choices[0]
        # 获取助手回复内容
        assistant = choice.message
        # 将助手的回复以dict形式加入消息列表 因为之前的数据是pydantic对象 相当于用ts约束了 但是修改了数据类型 需要重新转位dict
        messages.append(assistant_message_dict(assistant))
        # 如果助手没有工具可以调用, 则终止循环
        if not assistant.tool_calls:
            # 调用trigger_hooks函数 触发名为 'Stop'的hook 并传入当前消息列表作为参数 获取返回值force
            force = trigger_hooks("Stop", messages)
            # 判断force是否有值 即hook是否返回了信息需要处理
            if force:
                # 如果有值 则将其作为用户角色的消息添加到消息列表
                messages.append({"role": "user", "content": force})
                # 继续while循环 重新进入agent_loop流程
                continue
            return
        # 轮数计数器 rounds_since_todo 加 1
        rounds_since_todo += 1
        # 遍历所有工具调用
        for tool_call in assistant.tool_calls:
            # 获取工具名称
            name = tool_call.function.name
            # 解析工具参数 若为空则用空字典
            args = json.loads(tool_call.function.arguments or "{}")
            # 如果工具名称是compact
            if name == "compact":
                # 调用compact_history函数，对messages列表进行消息压缩处理
                messages[:] = compact_history(messages)
                # 跳出当前for tool_call循环
                break
            # 打印工具名称 蓝色高亮
            print(f"\x1b[36m> {name} {json.dumps(args, ensure_ascii=False)}\x1b[0m")
            # 如果没有通过权限检查 则打印拒绝信息 并跳过执行
            # 触发'PreToolUse'钩子 判断是否允许工具执行
            blocked = trigger_hooks("PreToolUse", name, args)
            # 如果被阻止(则blocked有返回值) 则进入下面的分支
            if blocked:
                # 将阻塞消息以'tool'角色形式加入消息列表
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": str(blocked),
                    }
                )
                # 跳过本次循环，继续处理下一个工具调用
                continue
            # 如果通过权限检查 则执行工具 获取输出结果
            output = execute_tool(name, args)
            # 触发 'PostToolUse'钩子 进行后置处理
            trigger_hooks("PostToolUse", name, args, output)
            # 把工具执行结果以特定格式加入消息列表
            messages.append(
                {"role": "tool", "tool_call_id": tool_call.id, "content": output}
            )
