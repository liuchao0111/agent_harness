# 导入json库 用于处理json数据
import json

# 从config模块导入默认设置的最大token数和主模型
from config import DEFAULT_MAX_TOKENS, MODEL_ID

# 从llm模块导入call_llm函数
from llm import call_llm

# 从prompt模块导入get_system_prompt函数
from prompt import get_system_prompt

# 从tools.executor模块导入execute_tool函数
from tools.executor import execute_tool

# 从utils模块导入assistant_message_dict函数
from utils import assistant_message_dict

# 从permission模块导入check_permission函数
from permission import check_permission


# 定义agent_loop函数 参数是消息列表
def agent_loop(messages: list):
    # 将最大的token数设置为默认值
    max_tokens = DEFAULT_MAX_TOKENS
    # 设置所用模型为主模型P
    model = MODEL_ID
    # 开始循环 直到return退出
    while True:
        # 获取系统提示词
        system = get_system_prompt()
        # 调用大模型获取回复
        response = call_llm(system, messages, max_tokens, model)
        # 取出回复中的第一个回复
        choice = response.choices[0]
        # 获取助手回复内容
        assistant = choice.message
        # 将助手的回复以dict形式加入消息列表 因为之前的数据是pydantic对象 相当于用ts约束了 但是修改了数据类型 需要重新转位dict
        messages.append(assistant_message_dict(assistant))
        # 如果助手没有工具可以调用, 则终止循环
        if not assistant.tool_calls:
            return
        # 遍历所有工具调用
        for tool_call in assistant.tool_calls:
            # 获取工具名称
            name = tool_call.function.name
            # 解析工具参数 若为空则用空字典
            args = json.loads(tool_call.function.arguments or "{}")
            # 打印工具名称 蓝色高亮
            print(f"\x1b[36m> {name} {json.dumps(args, ensure_ascii=False)}\x1b[0m")
            # 如果没有通过权限检查 则打印拒绝信息 并跳过执行
            reason = check_permission(name, args)
            if reason is not None:
                # 打印红色拒绝信息 显示拒绝原因
                print(f"\033[91m[!] 拒绝执行: {reason}\033[0m")
                # 把拒绝信息以特定格式加入消息列表
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": f"拒绝执行: {reason}",
                    }
                )
                # 跳过执行该工具
                continue
            # 如果通过权限检查 则执行工具 获取输出结果
            output = execute_tool(name, args)
            # 把工具执行结果以特定格式加入消息列表
            messages.append(
                {"role": "tool", "tool_call_id": tool_call.id, "content": output}
            )
