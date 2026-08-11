# 导入json库 用于处理json数据
import json

from background import (
    collect_background_results,
    should_run_background,
    start_background_task,
)

# 从config模块导入默认设置的最大token数和主模型
from config import (
    CONTEXT_LIMIT,
    CONTINUATION_PROMPT,
    DEFAULT_MAX_TOKENS,
    ESCALATED_MAX_TOKENS,
    MAX_RECOVERY_RETRIES,
    TODO_REMINDER_ROUNDS,
)

# 从hooks模块导入trigger_hooks函数
from cron import consume_cron_queue
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
from llm import RecoveryState, call_llm, is_prompt_too_long_error, with_retry

# 从memory模块导入load_memories函数
from memory import consolidate_memories, extract_memories, load_memories

# 从prompt模块导入get_system_prompt函数
from prompt import get_system_prompt

# 从tools.executor模块导入execute_tool函数
from tools.executor import execute_tool
from tools.handlers import todo_update_reminder

# 从utils模块导入assistant_message_dict函数
from utils import assistant_message_dict, message_text

# 定义变量rounds_since_todo 用于记录自上次todo_write调用以来的轮数
rounds_since_todo = 0

# reactive_compact_attempts = 0


# 定义agent_loop函数 参数是消息列表
def agent_loop(messages: list):
    # 声明全局变量rounds_since_todo
    global rounds_since_todo
    # 将最大的 token 数设置为默认值，并为本次用户任务保留恢复状态。
    max_tokens = DEFAULT_MAX_TOKENS
    state = RecoveryState()

    # 开始循环，直到返回最终回复。
    while True:
        # 先消费已经到点的 Cron 任务
        cron_jobs = consume_cron_queue()
        if cron_jobs:
            cron_notifications = []

            for job in cron_jobs:
                cron_notifications.append(
                    f"<cron_task>\n"
                    f"<id>{job.id}</id>\n"
                    f"<cron>{job.cron}</cron>\n"
                    f"<recurring>{job.recurring}</recurring>\n"
                    f"<prompt>{job.prompt}</prompt>\n"
                    f"</cron_task>"
                )
            messages.append(
                {
                    "role": "user",
                    "content": "\n\n".join(cron_notifications),
                }
            )
        # 从后台收集通知消息(如果有的话)
        bg_notifications = collect_background_results()
        # 如果收集到了后台通知
        if bg_notifications:
            # 将收集到的后台通知以用户消息格式追加到message消息列表
            messages.append({"role": "user", "content": "\n\n".join(bg_notifications)})
            # 打印注入后台通知的数量并以绿色高亮显示
            print(f"  \x1b[32m[注入] {len(bg_notifications)} 条后台通知\x1b[0m")
        # 获取系统提示词
        system = get_system_prompt()
        # 加载有关历史消息的记忆内容
        memories_content = load_memories(messages)
        # 如果记忆内容存在
        if memories_content:
            # 将记忆内容追加到系统提示词后 前面加两个换行符
            system += "\n\n" + memories_content
        # 如果有活跃的todo且N轮未更新的 把提醒写入sysytem
        todo_remainder = todo_update_reminder(rounds_since_todo, TODO_REMINDER_ROUNDS)
        if todo_remainder:
            system += "\n\n" + todo_remainder
            print(f"\x1b[33m][todo提醒] 连续{rounds_since_todo}轮未更新\x1b[0m]")
        # 创建一个用于存储消息压缩前内容的列表
        pre_compress = [
            # 对于messages中的每一个元素m,如果m是字典 则
            {"role": m.get("role"), "content": message_text(m)}
            # 遍历messages列表 只处理那些是字典累习惯的元素
            for m in messages
            if isinstance(m, dict)
        ]
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
        messages[:] = repair_messages_chain(messages)
        # 如果距离上次 todo 写入的论述大于等于3 且消息列表不为空
        # if rounds_since_todo >= 3 and messages:
        #     # 在消息列表中添加一条用户提醒 提示助手更新todo列表
        #     messages.append(
        #         {
        #             "role": "user",
        #             "content": "<reminder>请更新你的 todo 列表。<reminder>",
        #         }
        #     )
        #     print("\x1b[33m> 请更新你的 todo 列表。\x1b[0m")
        #     # 轮数计数器rounds_since_todo 复位为 0
        #     rounds_since_todo = 0
        # 调用大模型获取回复
        try:
            # bind loop variables into defaults so the retry closure uses the
            # values from this iteration rather than late-binding the loop
            # variables (especially `system`).
            response = with_retry(
                lambda system=system, messages=messages, max_tokens=max_tokens, model=state.current_model: (
                    call_llm(system, messages, max_tokens, model)
                ),
                state,
            )
        except (RuntimeError, OSError, ValueError) as e:
            # 如果捕获到的异常提示是提示词过长的错误
            if is_prompt_too_long_error(e):
                # 如果还没有尝试过reactive_compact方法进行压缩
                if not state.has_attempted_reactive_compact:
                    # 使用reactive_compact进行消息压缩
                    messages[:] = reactive_compact(messages)
                    # 标记已经尝试过reactive_compact
                    state.has_attempted_reactive_compact = True
                    # 继续while循环，重新尝试
                    continue
                # 如果压缩后仍然过长，则打印错误提示（红色字体）
                print("  \x1b[31m[不可恢复] compact 后仍然过长\x1b[0m")
                # 在消息列表中加入assistant角色的错误消息，提示上下文过大
                messages.append(
                    {"role": "assistant", "content": "[错误] 上下文过大，无法继续。"}
                )
                # 终止函数执行
                return
            # 获取异常的类型名称
            name = type(e).__name__
            # 打印不可恢复的错误信息，取错误内容的前100个字符（红色字体）
            print(f"  \x1b[31m[不可恢复] {name}: {str(e)[:100]}\x1b[0m")
            # 在消息列表中添加assistant角色的错误信息，包含异常类型和前200字符内容
            messages.append(
                {"role": "assistant", "content": f"[错误] {name}: {str(e)[:200]}"}
            )
            # 终止函数执行
            return
        # 取出回复中的第一个回复
        choice = response.choices[0]
        # 判断回复是否因最大长度被截断
        if choice.finish_reason == "length":
            # 如果还未升级max_tokens
            if not state.has_escalated:
                # 升级max_tokens至更大值
                max_tokens = ESCALATED_MAX_TOKENS
                # 标记已升级
                state.has_escalated = True
                # 打印升级提示
                print(
                    f"  \x1b[33m[max_tokens] 升级 {DEFAULT_MAX_TOKENS} -> {ESCALATED_MAX_TOKENS}\x1b[0m"
                )
                # 重新进入循环再次请求
                continue
            # 将助手的消息以dict形式加入消息列表
            messages.append(assistant_message_dict(choice.message))
            # 如果助手回复里包含工具调用
            if choice.message.tool_calls:
                # 遍历所有工具调用
                for tool_call in choice.message.tool_calls:
                    # 添加一条 tool 消息，提示输出被截断未执行
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": "[输出被截断，未能执行工具]",
                        }
                    )
                # 跳出本次循环，重新开始
                continue
            # 如果还在允许的最大恢复次数范围内
            if state.recovery_count < MAX_RECOVERY_RETRIES:
                # 添加一条用户消息，提示助手续写回复
                messages.append({"role": "user", "content": CONTINUATION_PROMPT})
                # 恢复计数加一
                state.recovery_count += 1
                # 打印续写提示
                print(
                    f"  \x1b[33m[max_tokens] 续写 {state.recovery_count}/{MAX_RECOVERY_RETRIES}\x1b[0m"
                )
                # 进入下一个循环尝试续写
                continue
            # 已达最大恢复重试次数，打印告警
            print("  \x1b[31m[max_tokens] 已达恢复上限\x1b[0m")
            # 终止函数执行
            return
        # 获取助手回复内容
        assistant = choice.message
        # 将助手的回复以dict形式加入消息列表 因为之前的数据是pydantic对象 相当于用ts约束了 但是修改了数据类型 需要重新转位dict
        messages.append(assistant_message_dict(assistant))
        # 如果助手没有工具可以调用, 则终止循环
        if not assistant.tool_calls:
            # 提取记忆
            extract_memories(pre_compress)
            # 合并记忆
            consolidate_memories()
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
            # 判断是否应该以后台任务方式运行工具
            if should_run_background(name, args):
                # 启动后台任务 并获取后台任务ID
                bg_id = start_background_task(tool_call.id, name, args)
                # 组织后台任务已启动的输出消息 包括任务ID 命令 通知方式
                # todo 后续增加 task_notification
                output = f"后台任务{bg_id}已启动,命令: {args.get('command', '')},完成后将通过"
            # 如果不是后台任务 则直接运行
            else:
                try:
                    # 执行工具函数，并获取输出
                    output = execute_tool(name, args)
                except (RuntimeError, ValueError, OSError) as e:
                    # 如果执行过程中发生已知异常，将异常信息作为输出内容
                    output = f"错误：{type(e).__name__}: {e}"
            # 如果通过权限检查 则执行工具 获取输出结果
            # 成功更新任务列表后，重新开始计算未更新 todo 的轮数。
            if name == "todo_write" and output.startswith("已更新"):
                rounds_since_todo = 0
            # 触发 'PostToolUse'钩子 进行后置处理
            trigger_hooks("PostToolUse", name, args, output)
            # 把工具执行结果以特定格式加入消息列表
            messages.append(
                {"role": "tool", "tool_call_id": tool_call.id, "content": output}
            )
