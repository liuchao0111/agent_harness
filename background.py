# 导入正则表达式模块
import re

# 导入线程模块
import threading

# 从工具包导入execute_tool函数
from tools.executor import execute_tool

# 定义一组代表 慢操作 的正则表达式
_SLOW_PATTERNS = [
    r"pip\s+install",  # 匹配pip install命令
    r"npm\s+install",  # 匹配npm install命令
    r"npm\s+ci",  # 匹配npm ci命令
    r"yarn\s+install",  # 匹配yarn install命令
    r"docker\s+build",  # 匹配docker build命令
    r"cargo\s+build",  # 匹配cargo build命令
    r"go\s+build",  # 匹配go build命令
    r"python\s+-m\s+pytest",  # 匹配python -m pytest命令
    r"python\s+-m\s+build",  # 匹配python -m build命令
    r"\bpytest\b",  # 匹配pytest命令
    r"\bmake\b",  # 匹配make命令
    r"\bdeploy\b",  # 匹配deploy命令
    r"npm\s+run\s+build",  # 匹配npm run build命令
    r"npm\s+run\s+test",  # 匹配npm run test命令
]

# 背景任务计数器 初始值为0
_bg_counter = 0

# 创建一个线程锁 用于保证对共享资源的操作的线程是安全的
background_lock = threading.Lock()

# 用于存储所有的后台任务 键为任务id 值为信息字典
background_tasks: dict[str, dict] = {}
# 用于存储所有的后台任务执行结果 键为任务id 值为信息字典
background_results: dict[str, str] = {}


# 判断是不是为慢操作
def is_slow_operation(tool_name: str, tool_input: dict) -> bool:
    # 如果不是bash类型的工具 则不是慢操作
    if tool_name != "bash":
        return False
    # 获取命令字符并转为小写
    cmd = tool_input.get("command", "").lower()
    # 对所有慢操作模式进行匹配 只要有一个匹配就返回True
    return any(re.search(pattern, cmd) for pattern in _SLOW_PATTERNS)


# 判断操作是否应在后台运行 tool_input是参数
def should_run_background(tool_name: str, tool_input: dict) -> bool:
    # 如果明确要求后台运行 则直接返回True
    if tool_input.get("run_in_background", False):
        return True
    # 否则根据是否为慢操作来判断
    return is_slow_operation(tool_name, tool_input)


# 启动一个后台任务
def start_background_task(tool_call_id: str, name: str, args: dict) -> str:
    # 声明使用全局变量
    global _bg_counter

    # 获取执行的命令内容
    command = args.get("command", "")

    # 定义工作线程的函数
    def worker():
        try:
            # 调用工具并获取结果
            result = execute_tool(name, args)

        # 捕获预期的运行时错误和系统相关错误并记录信息
        except (RuntimeError, OSError, ValueError) as e:
            result = f"错误: {type(e).__name__}: {e}"
        # 对共享资源加锁 修改任务状态和记录结果
        with background_lock:
            background_tasks[bg_id]["status"] = "completed"
            background_results[bg_id] = result

    # 先加锁 把任务信息写入后台任务字典
    with background_lock:
        # 计数器加1
        _bg_counter += 1
        # 生成后台任务ID 格式为bg_xxxx
        bg_id = f"bg_{_bg_counter:04d}"
        background_tasks[bg_id] = {
            "tool_call_id": tool_call_id,
            "command": command,
            "status": "running",
        }
    # 启动一个后台线程去执行worker任务(守护线程)
    threading.Thread(target=worker, daemon=True).start()
    # 打印后台任务派发的信息 便于调试和观察
    print(f"  \x1b[33m[后台] 已派发 {bg_id}: {command[:40]}\x1b[0m")
    # 返回后台任务id
    return bg_id


# 收集所有已完成的后台任务结果
def collect_background_results() -> list[str]:
    # 首先加锁 找出所有状态为completed的任务id
    with background_lock:
        ready_ids = [
            bid
            for bid, task in background_tasks.items()
            if task["status"] == "completed"
        ]
        # 用于存放通知消息的列表
        notifications = []
        # 遍历所有已经完成任务的id
        for bg_id in ready_ids:
            # 加锁 从任务和结果字典中弹出对应项
            with background_lock:
                task = background_tasks.pop(bg_id)
                output = background_results.pop(bg_id, "")
                # 如果输出内容超过200字符，则只取前200个字符作为概要
            summary = output[:200] if len(output) > 200 else output
            # 生成一个任务完成的通知字符串 并加入通知列表
            notifications.append(
                f"<task_notification>\n"
                f"<task_id>{bg_id}</task_id>\n"
                f"<status>completed</status>\n"
                f"<command>{task['command']}</command>\n"
                f"<summary>{summary}</summary>\n"
                f"</task_notification>"
            )
            # 打印后台完成的信息，包含任务id和命令摘要及输出字符数
            print(
                f"  \x1b[32m[后台完成] {bg_id}: {task['command'][:40]}（{len(output)} 字符）\x1b[0m"
            )
        # 返回所有通知消息的列表
        return notifications
