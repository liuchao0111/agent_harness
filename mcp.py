# 导入正则表达式模块
import re

# 导入类型提示 Callable，用于表示可调用对象
from typing import Callable

# 已连接的 MCP 客户端集合，键为字符串，值为 MCPClient 实例
mcp_clients: dict[str, "MCPClient"] = {}

# 定义非法字符的正则表达式（非 a-zA-Z0-9_-），用于名称标准化
_DISALLOWED_CHARS = re.compile(r"[^a-zA-Z0-9_-]")


# 定义 MCPClient 类，在 MCP 服务器上发现和调用工具
class MCPClient:
    """在 MCP 服务器上发现并调用工具。"""

    # 初始化方法，传入客户端名称
    def __init__(self, name: str):
        # 保存客户端名称
        self.name = name
        # 初始化工具列表，元素为字典
        self.tools: list[dict] = []
        # 初始化工具处理函数字典，键为工具名，值为处理函数
        self._handlers: dict[str, Callable] = {}

    # 注册方法，注册工具定义和处理函数
    def register(self, tool_defs: list[dict], handlers: dict[str, Callable]) -> None:
        """tools/list 发现。"""
        # 保存工具定义
        self.tools = tool_defs
        # 保存工具处理函数
        self._handlers = handlers

    # 工具调用方法， tools/call
    def call_tool(self, tool_name: str, args: dict) -> str:
        """tools/call。"""
        # 获取对应工具的处理函数
        handler = self._handlers.get(tool_name)
        # 如果没有找到处理函数，则返回错误信息
        if not handler:
            return f"MCP 错误：未知工具 '{tool_name}'"
        try:
            # 调用处理函数，并将参数解包
            return str(handler(**args))
        except Exception as e:
            # 如果调用出错，返回异常信息
            return f"MCP 错误：{e}"


# 工具名标准化，将非法字符替换为下划线
def normalize_mcp_name(name: str) -> str:
    # 使用正则表达式进行替换
    return _DISALLOWED_CHARS.sub("_", name)


# 构造 mock "docs" 服务器，返回对应 MCPClient
def _mock_server_docs() -> MCPClient:
    # 创建 MCPClient 实例，名称为 'docs'
    client = MCPClient("docs")
    # 注册工具定义及处理函数
    client.register(
        tool_defs=[
            {
                "name": "search",
                "description": "搜索文档。（只读）",
                "inputSchema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
            {
                "name": "get_version",
                "description": "获取 API 版本。（只读）",
                "inputSchema": {"type": "object", "properties": {}, "required": []},
            },
        ],
        handlers={
            "search": lambda query: f"[docs] 找到 3 条与 '{query}' 相关的结果",
            "get_version": lambda: "[docs] API v2.1.0",
        },
    )
    # 返回 mock 的 client 实例
    return client


# 构造 mock "deploy" 服务器，返回对应 MCPClient
def _mock_server_deploy() -> MCPClient:
    # 创建 MCPClient 实例，名称为 'deploy'
    client = MCPClient("deploy")
    # 注册工具定义及处理函数
    client.register(
        tool_defs=[
            {
                "name": "trigger",
                "description": "触发部署。",
                "inputSchema": {
                    "type": "object",
                    "properties": {"service": {"type": "string"}},
                    "required": ["service"],
                },
            },
            {
                "name": "status",
                "description": "查询部署状态。（只读）",
                "inputSchema": {
                    "type": "object",
                    "properties": {"service": {"type": "string"}},
                    "required": ["service"],
                },
            },
        ],
        handlers={
            "trigger": lambda service: f"[deploy] 已触发: {service}",
            "status": lambda service: f"[deploy] {service}: 运行中 (v1.4.2)",
        },
    )
    # 返回 mock 的 client 实例
    return client


# MOCK_SERVERS 字典，服务器名到工厂函数的映射
MOCK_SERVERS: dict[str, Callable[[], MCPClient]] = {
    "docs": _mock_server_docs,
    "deploy": _mock_server_deploy,
}


# 连接指定名称的 MCP 服务器
def connect_mcp(name: str) -> str:
    # 如果服务器已连接，直接返回已连接提示
    if name in mcp_clients:
        return f"MCP 服务器 '{name}' 已连接"
    # 根据名称获取对应的工厂函数
    factory = MOCK_SERVERS.get(name)
    # 如果名称找不到，则提示可用服务器名
    if not factory:
        available = ", ".join(MOCK_SERVERS.keys())
        return f"未知服务器 '{name}'。可用: {available}"
    # 创建 MCPClient 实例
    mcp_client = factory()
    # 存入已连接客户端集合
    mcp_clients[name] = mcp_client
    # 提取所有工具的名称
    tool_names = [t["name"] for t in mcp_client.tools]
    # 控制台打印已连接信息（着色）
    print(f"  \x1b[31m[mcp] 已连接: {name} → {tool_names}\x1b[0m")
    # 返回连接成功和工具信息
    return (
        f"已连接 MCP 服务器 '{name}'。"
        f"发现 {len(mcp_client.tools)} 个工具: {', '.join(tool_names)}"
    )


# 将 mcp 工具定义转换为 openai 格式的规范
def _mcp_tool_to_openai(prefixed: str, tool_def: dict) -> dict:
    # 从 tools.schema 导入 _fn_tool 方法
    from tools.schema import _fn_tool

    # 获取工具的输入 schema
    schema = tool_def.get("inputSchema", {})
    # 调用 _fn_tool 生成 openai 所需的工具描述
    return _fn_tool(
        prefixed,
        tool_def.get("description", ""),
        schema.get("properties", {}),
        schema.get("required", []),
    )


# 合并 builtin 工具和所有已连接 MCP 工具，返回统一的工具池和处理函数字典
def assemble_tool_pool() -> tuple[list[dict], dict]:
    """合并 builtin 与所有已连接 MCP 工具为统一池。"""
    # 导入内置工具定义
    # 导入内置工具处理函数
    from tools.handlers import TOOL_HANDLERS
    from tools.schema import TOOLS

    # 拷贝内置工具定义列表
    tools = list(TOOLS)
    # 拷贝内置工具处理函数字典
    handlers = dict(TOOL_HANDLERS)
    # 遍历所有已连接的 MCP 服务器
    for server_name, mcp_client in mcp_clients.items():
        # 标准化服务器名称
        safe_server = normalize_mcp_name(server_name)
        # 遍历当前服务器的所有工具
        for tool_def in mcp_client.tools:
            # 标准化工具名称
            safe_tool = normalize_mcp_name(tool_def["name"])
            # 拼接带前缀的工具名
            prefixed = f"mcp__{safe_server}__{safe_tool}"
            # 加入到工具总列表
            tools.append(_mcp_tool_to_openai(prefixed, tool_def))

            # 定义工厂函数返回专属 handler
            def _make_handler(client: MCPClient, tname: str):
                # 生成一个闭包 handler，实际调用 MCP 工具
                def _handler(**kwargs):
                    return client.call_tool(tname, kwargs)

                return _handler

            # 将处理函数加入 handlers 字典
            handlers[prefixed] = _make_handler(mcp_client, tool_def["name"])
    # 返回合并后的工具列表和处理函数字典
    return tools, handlers


# 获取当前已连接 MCP 服务器及其工具名摘要，用于 system prompt
def connected_mcp_summary() -> str:
    """供 system prompt 追加：当前已连接 MCP 及带前缀的工具名。"""
    # 若无连接的 mcp 客户端，返回空
    if not mcp_clients:
        return ""
    # 初始化摘要行列表，首行为说明
    lines = ["已连接 MCP 服务器（工具名带 mcp__server__tool 前缀）:"]
    # 遍历所有已连接的 mcp 客户端
    for server_name, mcp_client in mcp_clients.items():
        # 标准化服务器名
        safe_server = normalize_mcp_name(server_name)
        # 遍历服务器的每个工具
        for tool_def in mcp_client.tools:
            # 标准化工具名
            safe_tool = normalize_mcp_name(tool_def["name"])
            # 拼出全前缀工具名
            prefixed = f"mcp__{safe_server}__{safe_tool}"
            # 获取工具描述
            desc = tool_def.get("description", "")
            # 追加行到摘要列表
            lines.append(f"- {prefixed}: {desc}")
    # 返回摘要文本，按行连接
    return "\n".join(lines)


# 调用 connect_mcp 的包装函数
def run_connect_mcp(name: str) -> str:
    # 调用 connect_mcp 并返回结果
    return connect_mcp(name)
