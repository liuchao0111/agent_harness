# 定义一个函数 _fn_tool , 接收名称、描述 属性和必需字段列表 返回一个字典
def _fn_tool(
    name: str, description: str, properties: dict, required: list[str]
) -> dict:
    # 返回一个包含类型和函数信息的字典
    return {
        # 设定类型为'function'
        "type": "function",
        # 定义函数的具体内容
        "function": {
            # 函数名称
            "name": name,
            # 函数描述
            "description": description,
            # 参数设置 定义为一个对象 包含属性和必需字段
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


# 定义一个工具列表 包含一个通过_fn_tool函数生成的工具 bash命令执行
BASE_TOOLS = [
    # 定义 bash 命令行工具，参数为 command（字符串类型）
    _fn_tool(
        "bash",
        "执行一条 shell 命令。耗时操作可设 run_in_background=true 在后台运行。",
        {
            "command": {"type": "string"},
            "run_in_background": {"type": "boolean", "default": False},
        },
        ["command"],
    ),
    # 定义读取文件内容的工具 参数为path(字符串类型) 和 limit(整数类型), 其中 path为必需
    _fn_tool(
        "read_file",
        "读取文件内容",
        {"path": {"type": "string"}, "limit": {"type": "integer"}},
        ["path"],
    ),
    # 定义写入文件内容的工具 参数为path 和 content 都为字符串类型 均为必需
    _fn_tool(
        "write_file",
        "将写入文件",
        {"path": {"type": "string"}, "content": {"type": "string"}},
        ["path", "content"],
    ),
    # 定义编辑文件内容的工具 参数为path、old_text、new_text均为字符串类型 都为必需，进行精确替换一次
    _fn_tool(
        "edit_file",
        "在文件中精确替换一段文本(仅替换一次)。",
        {
            "path": {"type": "string"},
            "old_text": {"type": "string"},
            "new_text": {"type": "string"},
        },
        ["path", "old_text", "new_text"],
    ),
    # 定义使用 glob 模式查找文件的工具，参数为 pattern（字符串类型）
    _fn_tool(
        "glob", "按glob模式查找文件", {"pattern": {"type": "string"}}, ["pattern"]
    ),
    _fn_tool(
        "send_message",
        "通过 MessageBus 发送消息。发送方固定为当前 Agent 身份, 不可伪造。",
        {"to": {"type": "string"}, "content": {"type": "string"}},
        ["to", "content"],
    ),
]


TOOLS = [
    *BASE_TOOLS,
    _fn_tool(
        "spawn_subagent",
        "启动子 Agent 处理复杂子任务。仅返回最终结论。",
        {"description": {"type": "string"}},
        ["description"],
    ),
    _fn_tool(
        "todo_write",
        "创建并管理当前编码会话的任务列表。",
        {
            "todos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed"],
                        },
                    },
                    "required": ["content", "status"],
                },
            }
        },
        ["todos"],
    ),
    _fn_tool(
        "load_skill", "按名称加载技能的完整内容", {"name": {"type": "string"}}, ["name"]
    ),
    _fn_tool(
        "compact", "摘要较早对话以释放上下文空间。", {"focus": {"type": "string"}}, []
    ),
    _fn_tool(
        "create_task",
        "创建新任务，可选 blockedBy 依赖。",
        {
            "subject": {"type": "string"},
            "description": {"type": "string"},
            "blockedBy": {"type": "array", "items": {"type": "string"}},
        },
        ["subject"],
    ),
    _fn_tool(
        "list_tasks",
        "列出所有任务的状态、负责人与依赖",
        {},
        [],
    ),
    _fn_tool(
        "get_task",
        "按ID获取任务完整详情。",
        {
            "task_id": {"type": "string"},
        },
        ["task_id"],
    ),
    _fn_tool(
        "claim_task",
        "认领 pending 任务,设置 owner 并改为 in_progress",
        {"task_id": {"type": "string"}},
        ["task_id"],
    ),
    _fn_tool(
        "complete_task",
        "完成 in_progress任务 , 并报告下游解阻任务",
        {"task_id": {"type": "string"}},
        ["task_id"],
    ),
    _fn_tool(
        "delete_task",
        "删除任务",
        {"task_id": {"type": "string"}},
        ["task_id"],
    ),
    _fn_tool(
        "schedule_cron",
        "调度cron任务。cron为5段：分 时 日 月 周",
        {
            "cron": {"type": "string", "description": "5段cron表达式"},
            "prompt": {"type": "string", "description": "触发时注入消息"},
            "recurring": {"type": "boolean", "description": "true=循环 fasle=单次"},
            "durable": {"type": "boolean", "description": "true=持久化到磁盘"},
        },
        ["cron", "prompt"],
    ),
    _fn_tool("list_crons", "列出所有已注册的 cron 任务。", {}, []),
    _fn_tool(
        "cancel_cron",
        "按 ID 取消 cron 任务。",
        {"job_id": {"type": "string"}},
        ["job_id"],
    ),
    _fn_tool(
        "spawn_teammate",
        "启动自主队友Agent",
        {
            "name": {"type": "string"},
            "role": {"type": "string"},
            "prompt": {"type": "string"},
        },
        ["name", "role", "prompt"],
    ),
    # 定义 request_shutdown工具: 请求队友优雅关闭
    _fn_tool(
        "request_shutdown",
        "请求队友优雅关闭",
        {"teammate": {"type": "string"}},
        ["teammate"],
    ),
    # 定义 request_plan 工具：要求队友提交计划供审核
    _fn_tool(
        "request_plan",
        "要求队友提交计划供审核。",
        {"teammate": {"type": "string"}, "task": {"type": "string"}},
        ["teammate", "task"],
    ),
    # 定义 review_plan 工具：按 request_id 批准或拒绝已提交的计划
    _fn_tool(
        "review_plan",
        "按 request_id 批准或拒绝已提交的计划。",
        {
            "request_id": {"type": "string"},
            "approve": {"type": "boolean"},
            "feedback": {"type": "string"},
        },
        ["request_id", "approve"],
    ),
]


TEAMMATE_TOOLS = [
    *BASE_TOOLS,
    _fn_tool(
        "submit_plan",
        "向 Lead 提交计划以供审批；发送者会自动绑定为当前队友。",
        {"plan": {"type": "string"}},
        ["plan"],
    ),
    # 定义创建并管理当前编码会话的任务列表的工具，参数为 todos（数组类型，每个元素为对象，包含 content 和 status 字段）
    _fn_tool(
        "todo_write",
        "创建并管理当前编码会话的任务列表。",
        {
            "todos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed"],
                        },
                    },
                    "required": ["content", "status"],
                },
            }
        },
        ["todos"],
    ),
    _fn_tool(
        "load_skill",
        "按名称加载技能的完整内容。",
        {"name": {"type": "string"}},
        ["name"],
    ),
]
