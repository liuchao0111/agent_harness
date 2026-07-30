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
    _fn_tool("bash", "执行一条shell命令", {"command": {"type": "string"}}, ["command"]),
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
]


TOOLS = [
    *BASE_TOOLS,
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
        "spawn_subagent",
        "启动子 Agent 处理复杂子任务。仅返回最终结论。",
        {"description": {"type": "string"}},
        ["description"],
    ),
    _fn_tool(
        "load_skill", "按名称加载技能的完整内容", {"name": {"type": "string"}}, ["name"]
    ),
    _fn_tool(
        "compact", "摘要较早对话以释放上下文空间。", {"focus": {"type": "string"}}, []
    ),
]
