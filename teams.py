# 导入json模块，用于处理JSON数据
import json

# 导入threading模块，用于多线程
import threading

# 导入time模块，用于时间处理
import time
from contextvars import ContextVar

# 导入dataclass模块 用于定义数据类
from dataclasses import dataclass, field

# 从config模块导入常量和对象
from config import (
    DEFAULT_MAX_TOKENS,  # 默认最大token数
    MAILBOX_BACKUP_DIR,
    MAILBOX_DIR,  # 邮箱目录
    MODEL_ID,  # 主模型名称
    TEAMMATE_WAIT_TIMEOUT,  # Lead 等待队友结果的超时时间
    TEXT_ENCODING,  # 文本编码方式
    WORKDIR,  # 工作目录
    client,  # 大语言模型客户端
)

# 从history模块中导入repair_message_chain函数
from history import repair_messages_chain

# 从utils模块导入assistant_message_dict方法
from utils import assistant_message_dict

# 定义主管lead名字
LEAD_NAME = "lead"

# 导入random模块 用于生成 request_id
import random

# 队友LLM最大调用轮次(防止无限循环调用)
TEAMMATE_MAX_ROUNDS = 50

# 空闲超时时间(单位: 秒)
IDLE_TIMEOUT = 60

# 空闲轮询时间间隔(单位：秒)
IDLE_POLL_INTERVAL = 2

# 当前调用工具的 Agent 名称
current_agent: ContextVar[str] = ContextVar("current_agent", default="lead")

#  active_teammates: 队友名 → 线程对象
active_teammates: dict[str, threading.Thread] = {}

# 已 spawn 、尚未收到 type=result的队友(Lead 收尾屏障用)
pending_teammate_results: set[str] = set()

# agent 最大工作回合数
WORK_MAX_ROUNDS = 10

# MessageBus 文件读写锁
_bus_lock = threading.Lock()

# wait / 屏障轮训间隔
_WAIT_POLL_INTERVAL = 0.5


# 使用dataclass装饰器定义一个协议状态的数据结构
@dataclass
class ProtocolState:
    # 请求的唯一标识符
    request_id: str
    # 协议类型 可能为shutdown 或 plan_approval
    type: str  # shutdown | plan_approval
    # 请求发送者
    sender: str
    # 请求目标对象
    target: str
    # 状态, 可能为pending、approved 或者rejected
    status: str  # pending | approved | rejected
    # 附加信息
    payload: str
    # 创建时间 默认为当前时间
    created_at: float = field(default_factory=time.time)


# 用于存储所有挂起的协议请求 键为请求ID 值为协议状态对象
pending_requests: dict[str, ProtocolState] = {}


# 生成新的唯一请求ID
def new_request_id() -> str:
    # 随机生成6位数字 格式化为 req_xxxxxx的字符串
    return f"req_{random.randint(0, 999999):06d}"


# 消息总线类 用于管理不同agent间消息传递
class MessageBus:
    """基于文件的消息总线 每个Agent 一个 .jsonl 收件箱, 读取即消费。"""

    # 发送消息的方法
    def send(
        self,
        from_agent: str,  # 发送者
        to_agent: str,  # 接收者
        content: str,  # 消息内容
        msg_type: str = "message",  # 消息类型
        metadata: dict | None = None,  # 附加元数据 默认为None
    ):
        # 构造消息内容的字典
        msg = {
            "from": from_agent,  # 发送者
            "to": to_agent,  # 接收者
            "content": content,  # 消息内容
            "type": msg_type,  # 消息类型
            "ts": time.time(),  # 时间戳
            "metadata": metadata or {},
        }
        # 构造收件箱的路径
        inbox = MAILBOX_DIR / f"{to_agent}.jsonl"
        inbox_backup = MAILBOX_BACKUP_DIR / f"{to_agent}.jsonl"
        # 以追加模式写入收件箱，使用单个 with 语句管理多个上下文
        with _bus_lock, open(inbox, "a", encoding=TEXT_ENCODING) as f:
            # 将消息写为json字符串 每条一行
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
        with _bus_lock, open(inbox_backup, "a", encoding=TEXT_ENCODING) as f:
            # 将消息写为json字符串 每条一行
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
        # 控制台打印消息发送信息
        print(
            f"  \x1b[33m[总线] {from_agent} → {to_agent}[{msg_type}]: {content[:50]}\x1b[0m"
        )

    # 读取某agent收件箱的方法 与(send 共用锁 避免读写竞太丢信)
    def read_inbox(self, agent: str) -> list[dict]:
        # 构造收件箱路径
        inbox = MAILBOX_DIR / f"{agent}.jsonl"
        with _bus_lock:
            # 如果收件箱不存在 则返回空列表
            if not inbox.exists():
                return []
            # 读取所有消息 每行解析为json字典
            msgs = [
                json.loads(line)
                for line in inbox.read_text(encoding=TEXT_ENCODING).splitlines()
                if line.strip()
            ]
            # 读取后删除收件箱文件
            inbox.unlink()
        # 返回消息列表
        return msgs


# 实例话消息总线对象
BUS = MessageBus()


# 获取对应LLM 上下文 只取最新的tail消息 并修复tool链
def _teammate_llm_context(messages: list, tail: int = 20) -> list:
    # 如果消息数量大于tail 则最后取 tail 条 否则取全部
    window = messages[-tail:] if len(messages) > tail else list(messages)
    # 修复 tool 工具链 防止API错误 返回修复后的窗口信息
    return repair_messages_chain(window)


# 处理队友的收件箱消息 将协议消息(如关机批复、计划审批)等和普通消息区分开
def _process_teammate_inbox(
    teammate_name: str,  # 队友名称
    inbox: list[dict],  # 收件箱消息列表
    messages: list,  # 对话消息列表
) -> tuple[bool, list[dict]]:
    # 标记是否需要终止（收到关机请求）
    should_stop = False
    # 用于保存非协议消息
    non_protocol = []
    # 遍历收件箱中的每一条消息
    for msg in inbox:
        # 获取消息类型，默认为 'message'
        msg_type = msg.get("type", "message")
        # 获取元数据字典，默认为空字典
        meta = msg.get("metadata", {})
        # 获取请求 ID，默认为空字符串
        req_id = meta.get("request_id", "")
        # 如果收到关机请求类型的协议消息
        if msg_type == "shutdown_request":
            # 回复 Lead，说明已同意关闭
            BUS.send(
                teammate_name,  # 当前队友名称
                LEAD_NAME,  # Lead 名称
                "正在优雅关闭。",  # 消息内容
                "shutdown_response",  # 消息类型
                {
                    "request_id": req_id,
                    "approve": True,
                },  # 元数据，附带请求 ID 和批准信号
            )
            # 打印紫色的协议日志，说明已同意关闭
            print(f"  \x1b[35m[协议] {teammate_name} 已同意关闭（{req_id}）\x1b[0m")
            # 标记 should_stop 为 True
            should_stop = True
            # 跳出 for 循环，后续消息不再处理
            break
        # 如果收到计划审批响应
        if msg_type == "plan_approval_response":
            # 获取是否批准
            approve = meta.get("approve", False)
            # 如果批准
            if approve:
                # 向消息对话列表添加"计划已批准"的提示消息
                messages.append(
                    {"role": "user", "content": "[计划已批准] 请继续执行任务。"}
                )
            else:
                # 否则添加 "计划被拒绝"与反馈内容
                messages.append(
                    {"role": "user", "content": f"[计划被拒绝] 反馈:{msg['content']}"}
                )
            # 忽略后续代码 继续处理下条收件箱消息
            continue
        # 普通消息添加到 non_protocol 列表
        non_protocol.append(msg)
    # 返回是否需要停止循环和所有未被协议处理的普通消息
    return should_stop, non_protocol


# 判断队友是否仍有待 Lead 审批的计划。
def is_waiting_for_plan_approval(teammate_name: str) -> bool:
    return any(
        state.type == "plan_approval"
        and state.sender == teammate_name
        and state.status == "pending"
        for state in pending_requests.values()
    )


# 空闲轮询函数 用于处理队友的空闲状态。
def idle_poll(agent_name: str, messages: list) -> str:
    # 轮询 IDLE_TIMEOUT 秒，分为若干小轮，每一轮暂停 IDLE_POLL_INTERVAL 秒。
    for _ in range(IDLE_TIMEOUT // IDLE_POLL_INTERVAL):
        time.sleep(IDLE_POLL_INTERVAL)

        inbox = BUS.read_inbox(agent_name)
        if not inbox:
            continue

        should_stop, non_protocol = _process_teammate_inbox(agent_name, inbox, messages)
        if should_stop:
            return "shutdown"

        if non_protocol:
            messages.append(
                {
                    "role": "user",
                    "content": "<inbox>"
                    + json.dumps(non_protocol, ensure_ascii=False)
                    + "</inbox>",
                }
            )
        print(f"  \x1b[36m[idle] {agent_name} 收到 inbox 消息\x1b[0m")
        return "work"

    # 提交计划后必须等待 Lead 的明确审批，不应因普通空闲超时而退出。
    if is_waiting_for_plan_approval(agent_name):
        print(f"  \x1b[33m[idle] {agent_name} 仍在等待计划审批，继续等待\x1b[0m")
        return "waiting_plan_approval"

    print(f"  \x1b[31m[idle] {agent_name} 超时（{IDLE_TIMEOUT}s）\x1b[0m")
    return "timeout"


# 启动一个队友线程函数
def spawn_teammate_thread(name: str, role: str, prompt: str) -> str:
    # 如果请求启动的名字与 Lead 名字重复 则返回错误
    if name == LEAD_NAME:
        return f"错误: 不能使用保留名 '{LEAD_NAME}'"
    # 查找当前名字的队友线程是否存在
    existing = active_teammates.get(name)
    # 如果改线程已存在 则提示已存在
    if existing and existing.is_alive():
        return f"队友 '{name}' 已存在且仍在运行"
    # 如果线程对象存在但未存活 将其从 active_teammates移除
    if existing:
        active_teammates.pop(name, None)
        # 打印黄色日志说明旧线程被移除，可以重新启动
        print(f"  \x1b[33m[队友] {name} 旧线程已退出，允许重新启动\x1b[0m")
    # 构建 system prompt 指示Ai队友身份及工作指令
    system = (
        f"你是 '{name}'，角色为 {role}。"
        f"工作目录: {WORKDIR}。"
        f"使用工具完成任务。最终结果会在线程结束时自动发送给 '{LEAD_NAME}'。"
        "不要使用 send_message 重复发送最终结果；send_message 仅用于任务过程中的必要通信。"
        "收件箱由运行时自动检查，无需调用 check_inbox。"
        "收到 shutdown_request 时会自动关闭。"
        "需要 Lead 审批时，调用 submit_plan 提交计划；提交后保持等待，直到收到 plan_approval_response。"
        "收到批准后继续执行计划；收到拒绝后根据反馈修改并重新提交。"
    )

    # 队友线程主执行函数
    def run():
        # 延迟导入 避免与handler 循环依赖
        from tools.executor import execute_tool
        from tools.schema import TEAMMATE_TOOLS

        # 绑定当前线程的 Agent 身份，防止伪造  from_agent
        identity_token = current_agent.set(name)
        # 初始化消息 prompt作为第一条user消息
        messages = [{"role": "user", "content": prompt}]
        # 用于记录退出原因
        exit_reason = ""
        # LLM 调用轮次计数
        # llm_rounds = 0
        # try-finally 保证安全清理退出
        try:
            while True:
                # 若消息数量不超过3条 插入身份声明消息
                if len(messages) <= 3:
                    messages.insert(
                        0,
                        {
                            "role": "user",
                            "content": (
                                f"<identity>你是 '{name}', 角色: {role}。"
                                f"请继续你的工作。</identity>"
                            ),
                        },
                    )
                # 初始化是否退出循环标志
                should_shutdown = False
                # 进入最大循环轮数限制
                for _ in range(WORK_MAX_ROUNDS):
                    # 读取当前队友的收件箱消息
                    inbox = BUS.read_inbox(name)
                    # 如果收件箱有消息 则进行处理
                    if inbox:
                        # 处理协议消息和非协议消息
                        should_stop, non_protocol = _process_teammate_inbox(
                            name, inbox, messages
                        )
                        # 若收到关闭信号 则设置标志跳出循环
                        if should_stop:
                            should_shutdown = True
                            break
                        # 如果有非协议消息 将其添加到对话消息列表
                        if non_protocol:
                            messages.append(
                                {
                                    "role": "user",
                                    "content": (
                                        f"<inbox>{json.dumps(non_protocol, ensure_ascii=False)}</inbox>"
                                    ),
                                }
                            )
                    # 尝试请求 LLM 补全
                    try:
                        response = client.chat.completions.create(
                            model=MODEL_ID,
                            messages=[
                                {"role": "system", "content": system},
                                *_teammate_llm_context(messages),
                            ],
                            tools=TEAMMATE_TOOLS,
                            max_tokens=DEFAULT_MAX_TOKENS,
                        )
                    except (ConnectionError, RuntimeError, ValueError) as e:
                        # 明确捕获可能的网络/运行时/值错误并退出循环
                        exit_reason = f"LLM 错误: {type(e).__name__}: {e}"
                        print(f"  \x1b[31m[队友] {name} {exit_reason}\x1b[0m")
                        break
                        #     # 得到 assistant 返回的第一个回复消息对象
                    assistant = response.choices[0].message
                    # 格式化并加入通知消息历史
                    messages.append(assistant_message_dict(assistant))
                    # 如果 assistant 没有调用任何工具 跳出当前循环
                    if not assistant.tool_calls:
                        break
                    # 有工具调用时 依次处理一项工具调用
                    for tool_call in assistant.tool_calls:
                        tname = tool_call.function.name
                        args = json.loads(tool_call.function.arguments or "{}")
                        preview = json.dumps(args, ensure_ascii=False)
                        print(f"  \x1b[36m[{name}] > {tname} {preview[:100]}\x1b[0m")
                        # 工具异常不打崩整条线程
                        try:
                            output = execute_tool(tname, args)
                            print(
                                f"  \x1b[32m[{tname}] < {output} spawn_teammate_thread/output\x1b[0m"
                            )
                        except (RuntimeError, ValueError) as e:
                            output = f"错误: {type(e).__name__}: {e}"
                            print(f"  \x1b[31m[{name}] {output}\x1b[0m")
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": output,
                            }
                        )
                # 如果应当退出主循环 则跳出外层while
                if should_shutdown:
                    break
                # 进入空闲轮询 自动认领时可设置wt_ctx
                idle_result = idle_poll(name, messages)
                if idle_result == "shutdown":
                    break
                # 提交计划后每满一个空闲周期继续等待审批响应。
                if idle_result == "waiting_plan_approval":
                    continue
                if idle_result == "timeout":
                    exit_reason = f"idle 超时({IDLE_TIMEOUT}s)"
                    break
            summary = exit_reason or "完成"
            #  从后往前遍历消息历史 寻找最后一条有效的助手回复
            for msg in reversed(messages):
                # 判断当前消息是否为助手角色且包含内容
                if msg.get("role") == "assistant" and msg.get("content"):
                    # 取出消息中的内容字段
                    content = msg["content"]
                    # 确认内容是非空字符串
                    if isinstance(content, str) and content.strip():
                        # 用该内容 更新summary
                        summary = content
                        # 找到后立即跳出循环
                        break
            # 通过消息总线将 summary 作为结果发送给lead
            BUS.send(name, LEAD_NAME, summary, "result")
            # 打印队友已结束的绿色提示信息
            print(f"  \x1b[32m[队友] {name} spawn_teammate_thread 已结束\x1b[0m")
        finally:
            print(f"  \x1b[32m[最终] {name} spawn_teammate_thread finally\x1b[0m")
            current_agent.reset(identity_token)
            active_teammates.pop(name, None)

    # 创建线程对象 目标为run函数 设置为守护线程
    thread = threading.Thread(target=run, daemon=True)
    # 将线程注册到active_teammates字典
    active_teammates[name] = thread
    # 标记待回收 result , 供Lead 收尾屏障等待
    pending_teammate_results.add(name)
    # 启动线程
    thread.start()
    # 启动后打印青色控制台日志
    print(f"  \x1b[36m[队友] 已启动 spawn_teammate_thread {name}，角色 {role}\x1b[0m")
    return f"队友 '{name}' 已启动，角色 {role}。完成后将向 lead 发送 result；可用 await_teammates 等待。"


# 收件箱消息格式化为文本字符串(含 type / request_id 便于 review_plan)
def format_inbox_messages(msgs: list[dict]) -> str:
    lines = []
    for m in msgs:
        # 从消息字典中获取 "metadata"字段 没有则默认为空字典
        meta = m.get("metadata", {})
        # 从metadata 字典中获取 "request_id" 字段 没有则默认为空字符串
        req_id = meta.get("request_id", "")
        # 如果request_id存在，则格式为“[类型 req:request_id]”，否则为“[类型]”
        tag = (
            f" [{m.get('type', 'message')} req:{req_id}]"
            if req_id
            else f" [{m.get('type', 'message')}]"
        )
        # 协议消息突出 request_id
        # header = f"来自 {m['from']} [{msg_type}]"
        lines.append(f"来自 {m['from']}{tag}: {m['content'][:200]}")
    return "[收件箱]\n" + "\n".join(lines)


# 匹配响应 根据request_id 关联并校验响应类型
def match_response(response_type: str, request_id: str, approve: bool) -> None:
    # 通过 request_id 获取协议状态
    state = pending_requests.get(request_id)
    # 未找到协议状态
    if not state:
        print(f"  \x1b[31m[协议] 未知 request_id: {request_id}\x1b[0m")
        return
    # 校验shut_down 类型的请求响应类型是否正确
    if state.type == "shutdown" and response_type != "shutdown_response":
        print(
            f"  \x1b[31m[协议] 类型不匹配: 期望 shutdown_response，"
            f"实际 {response_type}\x1b[0m"
        )
        return
    # plan_approval_response 的接收方是队友；计划状态在 Lead 审批时由
    # run_review_plan() 直接更新，因此不会在 Lead 收件箱中路由。
    # 判断该请求状态是否已处理过，避免重复处理
    if state.status != "pending":
        print(f"  \x1b[33m[协议] {request_id} 已是 {state.status}，忽略重复响应\x1b[0m")
        return
    # 根据 approve参数设置状态为通过或者拒绝
    state.status = "approved" if approve else "rejected"
    # 选择显示的icon (勾或者叉)
    icon = "✓" if approve else "✗"
    # 通过或拒绝对应不同颜色
    color = "32" if approve else "31"
    # 打印协议处理结果信息
    print(
        f"  \x1b[{color}m[协议] {state.type} {icon} "
        f"({request_id}: {state.status})\x1b[0m"
    )


def _mark_results_received(msgs: list[dict]) -> None:
    """根据收件箱中的result消息 清楚pending_teammate_results 集合中的名字"""
    for msg in msgs:
        if msg.get("type") == "result":
            sender = msg.get("from")
            if sender and sender in pending_teammate_results:
                pending_teammate_results.discard(sender)
                print(f"  \x1b[32m[屏障] 收到队友 {sender} 的结果，清除屏障\x1b[0m")


def list_pending_teammates() -> list[str]:
    """返回当前等待结果的队友名字列表"""
    return list(pending_teammate_results)


# 定义函数 读取Lead收件箱。 参数route_protocol 表示是否需要路由协议响应
def consume_lead_inbox(route_protocol: bool = True) -> list[dict]:
    # 读取 LEAD_NAME 的收件箱消息列表
    msgs = BUS.read_inbox(LEAD_NAME)
    # 如果消息列表为空 则直接返回空列表
    if not msgs:
        return []
    # result 到达即解除屏障等待
    _mark_results_received(msgs)
    # 如果需要路由协议响应
    if route_protocol:
        # 遍历所有消息
        for msg in msgs:
            # 从消息中获取metadata,默认为空字典
            meta = msg.get("metadata", {})
            # 从 metadata 中获取 request_id 默认为空字符串
            req_id = meta.get("request_id", "")
            # 获取消息类型
            msg_type = msg.get("type", "")
            # 如果有 request_id 且消息类型以 "_response" 结尾
            if req_id and msg_type.endswith("_response"):
                # 从 metadata 中获取 approve 字段，默认为 False
                approve = meta.get("approve", False)
                # 调用 match_response 方法，路由协议响应
                match_response(msg_type, req_id, approve)
    # 返回读取到的所有消息
    return msgs


# 注入lead的收件箱消息到对话消息列表
def inject_lead_inbox(message: list) -> int:
    # 调用consume_lead_inbox读取lead收件箱消息，开启路由协议
    inbox = consume_lead_inbox(route_protocol=True)
    # 如果没有 返回0
    if not inbox:
        return 0
    # 把收件箱内容格式化为一条user消息 添加到对话消息列表
    message.append({"role": "user", "content": format_inbox_messages(inbox)})
    # 控制台打印注入了多少条消息
    print(f"  \x1b[33m[收件箱] 已注入 {len(inbox)} 条消息\x1b[0m")
    return len(inbox)


# 判断指定名字的队友线程是否在运行
def is_teammate_running(name: str) -> bool:
    # 从active_teammates 字典中获取指定名字的线程对象
    thread = active_teammates.get(name)
    # 判断线程对象是否存在且线程是否存活
    return thread is not None and thread.is_alive()


# 等待所有队友完成任务 返回完成数量
def wait_for_teammates(
    names: list[str] | None = None, timeout: float | None = None
) -> str:
    """
    阻塞等待指定(或全部 pending) 队友的result
    等待期间轮训消费 lead 收件箱中的消息 返回汇总文本供tool_result 使用
    """
    timeout = TEAMMATE_WAIT_TIMEOUT if timeout is None else timeout
    targets = set(names) if names else set(pending_teammate_results)
    if not targets:
        return "没有待等待的队友 result"
    # 只等待仍在pending中的名字
    targets &= pending_teammate_results
    if not targets:
        return "所有队友 result 已收到"

    print(
        f"  \x1b[35m[屏障] 等待队友 result: {', '.join(sorted(targets))}"
        f"（超时 {timeout:.0f}s）\x1b[0m"
    )

    deadline = time.time() + timeout
    collected: list[dict] = []
    while time.time() < deadline:
        inbox = consume_lead_inbox(route_protocol=False)
        if inbox:
            collected.extend(inbox)
        remaining = targets & pending_teammate_results
        if not remaining:
            break
        # 线程已死但尚未读到result 再读一轮后由调用方prune
        if all(not is_teammate_running(n) for n in targets):
            inbox = consume_lead_inbox(route_protocol=False)
            if inbox:
                collected.extend(inbox)
            # 仍无 result 则视为异常结束 解除挂起以免死等
            for n in list(remaining):
                if n in pending_teammate_results and not is_teammate_running(n):
                    pending_teammate_results.discard(n)
                    print(f"  \x1b[31m[屏障] 队友 {n} 已结束，清除屏障\x1b[0m")
            break
        time.sleep(_WAIT_POLL_INTERVAL)
    remaining = sorted(targets & pending_teammate_results)
    parts = []
    if collected:
        parts.append(format_inbox_messages(collected))
    if remaining:
        parts.append(
            f"仍有 {len(remaining)} 个队友未完成：{', '.join(sorted(remaining))}"
        )
    else:
        parts.append("所有队友 result 已收到")
    return "\n".join(parts)


def apply_teammate_stop_barrier(messages: list) -> str | None:
    """
    Lead 无 tool_calls 准备 Stop 时调用。
    若仍有 pending result：阻塞等待 → 注入收件箱 → 返回应追加的 user 提示；
    无 pending 则返回 None（允许真正退出）。
    """
    pending = list_pending_teammates()
    if not pending:
        # 退出前再吸一次吃到的信(不强制continue，除非强制有新信)
        n = inject_lead_inbox(messages)
        if n:
            return "[队友屏障] 退出前从收件箱注入了迟到消息，请据此更新回复后再结束。"
        return None
    status = wait_for_teammates(names=pending, timeout=TEAMMATE_WAIT_TIMEOUT)
    inject_lead_inbox(messages)
    still = list_pending_teammates()
    hint = (
        f"[队友屏障] {status}\n"
        "请根据收件箱中的队友结果汇总回复用户；"
        "不要在未看到 result 时声称任务已完成。"
    )
    if still:
        hint += f"\n仍在等待: {', '.join(still)}"
    print("  \x1b[35m[屏障] Stop 已拦截，注入汇总后继续一轮\x1b[0m")
    return hint


# 定义函数 读取Lead收件箱
def consume_inbox(agent_name: str) -> list[dict]:
    # 读取LEAD_NAME 的收件箱消息列表
    msgs = BUS.read_inbox(agent_name)
    # 如果消息列表为空 则直接返回空列表
    if not msgs:
        return []
    # Lead 侧消费时同样解除 pending
    if agent_name == LEAD_NAME:
        _mark_results_received(msgs)
    # 返回读取到的所有消息
    return msgs


# 请求优雅关闭某队友 向其发起关机协议消息
def run_request_shutdown(teammate: str) -> str:
    # 生成新的唯一请求ID
    req_id = new_request_id()
    # 在pending_requests 字典中记录关机请求的protocol状态
    pending_requests[req_id] = ProtocolState(
        request_id=req_id,  # 请求编号
        type="shutdown",  # 协议类型
        sender=LEAD_NAME,  # 发起者为Lead
        target=teammate,  # 目标为指定队友名
        status="pending",  # 当前状态为等待处理
        payload="",  # 没有关联负载
    )
    # 向队友发送关机请求消息 包括元数据中的请求ID
    BUS.send(
        LEAD_NAME, teammate, "请优雅关闭。", "shutdown_request", {"request_id": req_id}
    )
    # 打印带颜色的控制日志 显示已发送关机请求
    print(f"  \x1b[35m[协议] shutdown_request → {teammate}（{req_id}）\x1b[0m")
    # 正常情况下返回已发送请求的说明
    return f"已向{teammate} 发送关闭请求(req: {req_id})"


# 要求队友提交计划 即发送消息让队友编写任务计划 只能主Agent应用
def run_request_plan(teammate: str, task: str) -> str:
    # 向队友收件箱发送请求 要求其提交计划 消息类型为普通message
    BUS.send(LEAD_NAME, teammate, f"请提交计划: {task}", "message")
    # 否则返回已成功请求队友提交计划
    return f"已要求 {teammate} 提交计划"


# 队友向 Lead 提交计划以待审批。
def run_submit_plan(plan: str) -> str:
    # 发送者固定为当前 Agent 身份，避免由模型伪造。
    from_name = current_agent.get()
    # 生成计划审批请求新的request_id
    req_id = new_request_id()
    # 在pending_requests 保存本次请求的状态对象
    pending_requests[req_id] = ProtocolState(
        request_id=req_id,  # 当前 request_id
        type="plan_approval",  # 协议类型为“计划审批”
        sender=from_name,  # 谁发的
        target=LEAD_NAME,  # 发给Lead
        status="pending",  # 当前状态为等待审批
        payload=plan,  # 计划内容
    )
    # 通过BUS 发送计划审批请求协议消息 content 是计划内容
    BUS.send(
        from_name, LEAD_NAME, plan, "plan_approval_request", {"request_id": req_id}
    )
    # 返回提示文本 包含request_id
    return f"计划已提交({req_id})。等待审批..."


# Lead 对队友提交的计划进行审批(批准或者拒绝)，并进行响应 只能主Agent应用
def run_review_plan(request_id: str, approve: bool, feedback: str = "") -> str:
    # 从pending_requests 字典中查找请求状态对象
    state = pending_requests.get(request_id)
    # 如果找不到该请求 返回提示
    if not state:
        return f"未找到请求 {request_id}"
    # 如果该请求已经不在待处理状态 说明已操作过 返回对应状态
    if state.status != "pending":
        return f"请求 {request_id} 已是 {state.status}"
    # 根据 approve 设定当前请求的最终状态
    state.status = "approved" if approve else "rejected"
    # 向队友发回计划审批协议响应 带上审批反馈和结果
    BUS.send(
        LEAD_NAME,  # 发送者
        state.sender,  # 接收者
        feedback or ("已批准" if approve else "已拒绝"),  # 消息内容
        "plan_approval_response",  # 消息类型
        {"request_id": request_id, "approve": approve},  # 元数据
    )
    # 设定审批通过或者拒绝的标志字符
    icon = "✓" if approve else "✗"
    # 控制台输出审批过程日志，带颜色
    print(f"  \x1b[32m[协议] 计划 {icon}（{request_id}）\x1b[0m")
    # 返回描述审批结果的字符串
    return f"计划{'已批准' if approve else '已拒绝'}（{request_id}）"
