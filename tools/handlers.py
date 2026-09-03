import glob as g

# 导入os模块 用于与操作系统交互
import os

# 导入subprocess模块 用于执行子进程
import subprocess
from pathlib import Path

# 从config模块导入TEXT_ENCODING和WORKDIR，用于指定文本编码和工作目录
from config import TEXT_ENCODING, WORKDIR

# 从 skills模块 导入 load_skill函数
from cron import cancel_job, cron_lock, schedule_job, scheduled_jobs
from mcp import run_connect_mcp
from skills import load_skill

# 从tasks模块导入create_task函数
from tasks import (
    claim_task,
    complete_task,
    create_task,
    delete_task,
    get_task,
    list_tasks,
)
from teams import (
    BUS,
    LEAD_NAME,
    consume_inbox,
    current_agent,
    format_inbox_messages,
    is_teammate_running,
    run_request_plan,
    run_request_shutdown,
    run_review_plan,
    run_submit_plan,
    spawn_teammate_thread,
    wait_for_teammates,
)

# 从utils模块中导入decode_subprocess_output函数 用于解码子进程输出
from utils import decode_subprocess_output, safe_path
from worktrees import (
    run_create_worktree,
    run_keep_worktree,
    run_remove_worktree,
)


# 定义run_bash函数,接收一个字符串类型参数command,并返回字符串
def run_bash(
    command: str, run_in_background: bool = False, cwd: Path | None = None
) -> str:
    # 如果当前操作系统是Windows系统 并且命令是'date'(忽略前后空白并转位小写)
    # if os.name == "nt" and command.strip().lower() == "date":
    #     # 将命令改为Windows下同时输出日期和时间的命令
    #     command = "date /t & time /t"
    # 定义危险命令的列表
    dangerous = ["rm -rf / ", "sudo", "shutdown", "rebot", "> /dev/"]
    # 如果命令中包含任何一个危险的命令
    if any(d in command for d in dangerous):
        # 返回错误提示 拦截执行危险命令
        return "错误: 危险命令已拦截"
    # 尝试执行命令 捕获异常
    try:
        # 使用subprocess.run 运行命令
        r = subprocess.run(
            command,  # 要执行的命令
            shell=True,  # 在shell中执行
            cwd=str(cwd) if cwd else os.getcwd(),  # 当前工作目录设置为当前路径
            check=False,  # 明确指定不抛出子进程非零退出码的异常
            # text=True,
            capture_output=True,  # 捕获标准输出和标准错误
            timeout=20,  # 超时时间为120秒
        )
        # 解码输出内容 合并stdout和stderr 并去除首尾空白
        out = decode_subprocess_output((r.stdout or b"") + (r.stderr or b"")).strip()
        return out[:5000] if out else "  (无输出) "
    except subprocess.TimeoutExpired:
        return "错误: 超时(120秒)"
    # 捕获文件未找到OS错误 返回详细错误信息
    except (FileNotFoundError, OSError) as e:
        return f"错误: {e}"


# 定义读取文件的处理函数 参数为文件路径和可选的行数限制
def run_read(path: str, limit: int | None = None, cwd: Path | None = None) -> str:
    # 尝试执行以下代码
    try:
        # 使用safe_path校验并控制文件路径,按指定编码读取内容并按行分割
        lines = safe_path(path, cwd).read_text(encoding=TEXT_ENCODING).splitlines()
        # 如果有行数限制且文件超过限制
        if limit and limit < len(lines):
            # 截取前limit行，并在最后添加提示剩余行的说明
            lines = lines[:limit] + [f"...(还有{len(lines) - limit}行)"]
        # 将行列表拼接为字符串返回
        return "\n".join(lines)
    # 捕获所有异常并返回错误信息
    except (FileNotFoundError, PermissionError, OSError, UnicodeDecodeError) as e:
        return f"错误: {e}"


# 定义写文件函数 参数为路径和内容
def run_write(path: str, content: str, cwd: Path | None = None) -> str:
    # 尝试执行以下代码
    try:
        # 使用safe_path校验并获取目标文件路径
        file_path = safe_path(path, cwd)
        # 确保文件父目录存在 若不存在则创建
        file_path.parent.mkdir(parents=True, exist_ok=True)
        # 按照指定编码写入内容到文件
        file_path.write_text(content, encoding=TEXT_ENCODING)
        # 返回写入成功的提示语句, 包括字节数
        return f"已写入{len(content)} 字节到{path}"
    # 捕获所有异常并返货错误信息
    except (PermissionError, OSError, UnicodeEncodeError) as e:
        return f"错误 {e}"


# 定义编辑文件函数 参数为路径 、 待替换旧文本、和新文本
def run_edit(path: str, old_text: str, new_text: str, cwd: Path | None = None) -> str:
    # 尝试执行以下代码
    try:
        # 使用safe_path校验并获取目标文件路径
        file_path = safe_path(path, cwd)
        # 读取文件的全部内容(默认编码)
        text = file_path.read_text()
        # 如果旧文本不在内容中
        if old_text not in text:
            # 返回错误提示 未找到制定文本
            return f"错误 在{path}中 找到制定文本"
        # 替换第一次出现的旧文本为新文本, 并写回文件
        file_path.write_text(
            text.replace(old_text, new_text, 1), encoding=TEXT_ENCODING
        )
        # 返回编辑成功的提示
        return f"已编辑 {path}"
    except (FileNotFoundError, PermissionError, OSError, UnicodeDecodeError) as e:
        return f"错误: {e}"


# 定义glob通配符路径匹配参数 , 参数为模式
def run_glob(pattern: str, cwd: Path | None = None) -> str:
    # 尝试执行以下代码
    try:
        # 初始化结果列表
        results = []
        # 使用cwd作为根目录查找pattern，未指定时回退到WORKDIR
        root = cwd if cwd is not None else WORKDIR
        # 遍历所有匹配到的路径，根目录为WORKDIR
        for match in g.glob(pattern, root_dir=root):
            # 检查匹配到的路径是否相对WORKDIR安全
            if (root / match).resolve().is_relative_to(root):
                # 将安全的匹配结果加入结果列表
                results.append(str(match))
        # 如果结果非空 , 拼接为字符串返回 ，否则无法返回无匹配的提示
        return "\n".join(results) if results else "（无匹配"
    except (OSError, PermissionError) as e:
        return f"错误: {e}"


# 定义全局变量CURRENT_TODOS，用于存储当前的任务列表 ，类型为list[dict]
CURRENT_TODOS: list[dict] = []


def todo_update_reminder(rounds_since: int, threshold: int):
    # 找出尚未完成的 TODO
    active = [
        todo
        for todo in CURRENT_TODOS
        if todo.get("status") in ("pending", "in_progress")
    ]
    # 没有活跃任务，或尚未达到提醒阈值时不提醒
    if not active or rounds_since < threshold:
        return None
    lines = [
        f"[ToDo提醒]有未完成的任务，且连续{rounds_since}轮未调用todo_write,请更新进度",
        "当前的任务:",
    ]
    for todo in CURRENT_TODOS:
        lines.append(f"- [{todo.get('status', '?')}] {todo.get('content', '')}")
    return "\n".join(lines)


# 定义run_todo_write函数 ，参数为todos列表，返回字符串
def run_todo_write(todos: list) -> str:
    # 声明使用全局变量CURRENT_TODOS
    global CURRENT_TODOS
    # 遍历todos列表 获取每个任务及其索引
    for i, t in enumerate(todos):
        # 如果任务中缺少content或status字段
        if "content" not in t or "status" not in t:
            # 返回错误提示 指出缺少字段的位置
            return f"错误 todos[{i}] 缺少 content 或 status"
        # 如果任务的status不是允许的三种状态
        if t["status"] not in ("pending", "in_progress", "completed"):
            # 返回错误提示 指出状态无效
            return f"错误： todos[{i}] 的状态无效 : {t['status']}"
    # 校验全部通过后 更新全局任务列表
    CURRENT_TODOS = todos
    # 初始化显示用的lines列表 第一行为标题 并加黄颜色
    lines = ["\n\x1b[33m## 当前任务\x1b[0m"]
    # 遍历当前所有任务
    for t in CURRENT_TODOS:
        # 根据任务状态，选择不同的彩色标签
        icon = {
            "pending": "\x1b[33m等待中\x1b[0m",
            "in_progress": "\x1b[36m处理中\x1b[0m",
            "completed": "\x1b[32m已完成\x1b[0m",
        }[t["status"]]
        # 将格式化后的任务内容和标签加入lines
        lines.append(f"  [{icon}] {t['content']}")
    # 将所有内容组合成字符串打印到标准输出
    print("\n".join(lines))
    # 返回已更新任务数的字符串提示
    return f"已更新 {len(CURRENT_TODOS)} 个任务"


# 定义 run_create_taks函数 用于创建新任务
def run_create_task(
    subject: str, description: str = "", blockedBy: list[str] | None = None
) -> str:
    # 调用create_task函数 创建任务对象
    task = create_task(subject, description, blockedBy)
    # 若存在阻塞依赖项则格式化为依赖描述字符串 否则为空字符串
    deps = f" (blockedBy: {', '.join(blockedBy)}) " if blockedBy else ""
    # 以蓝色ANSI颜色打印创建成功的任务主题及依赖信息
    print(f"  \x1b[34m[创建] {task.subject}{deps}\x1b[0m")
    # 返回已创建任务的ID、主题及依赖信息提示
    return f"已创建 {task.id}: {task.subject}{deps}"


# 定义run_list_tasks函数 用于列出所有任务 返回字符串
def run_list_tasks() -> str:
    # 调用list_tasks获取所有任务列表
    tasks = list_tasks()
    # 如果任务列表为空
    if not tasks:
        # 返回暂无任务的信息
        return "暂无任务 使用create_task添加"
    # 初始化用于存储显示行的空列表
    lines = []
    # 遍历所有任务
    for t in tasks:
        # 根据任务状态获取对应的中文状态标签
        icon = {
            # pending状态对应“等待中”
            "pending": "等待中",
            # in_progress状态对应“处理中”
            "in_progress": "处理中",
            # completed状态对应“已完成”
            "completed": "已完成",
        }.get(t.status, "?")
        # 若任务有阻塞依赖则格式化依赖信息，否则为空字符串
        deps = f" (blockedBy: {' ,'.join(t.blockedBy)})" if t.blockedBy else ""
        # 若任务有负责人则格式化负责人信息 否则为空字符串
        owner = f" [{t.owner}]" if t.owner else ""
        # 如果有绑定 worktree，追加显示
        wt = f" (wt:{t.worktree})" if t.worktree else ""
        # 将格式化后的任务信息行加入lines列表
        lines.append(f"  {icon} {t.id}: {t.subject} [{t.status}]{owner}{deps}{wt}")
    # 将所有行用换行符拼接成字符串后返回
    return "\n".join(lines)


# 定义run_get_task函数 按任务ID获取任务详情 返回字符串
def run_get_task(task_id: str) -> str:
    # 尝试获取指定ID任务
    try:
        # 调用get_task(task_id)
        return get_task(task_id)
    except FileNotFoundError:
        # 返回未找到任务的错误提示
        return f"错误: 未找到任务{task_id}"


# 定义 run_claim_task函数 认领指定任务 返回字符串
def run_claim_task(task_id: str) -> str:
    return claim_task(task_id)


# 定义 run_complete_task函数 完成指定任务 返回字符串
def run_complete_task(task_id: str) -> str:
    return complete_task(task_id)


# 定义run_scan_unclaimed_tasks函数 扫描未被认领且所有依赖已完成任务 返回字符串
def run_scan_unclaimed_tasks(task_id: str) -> str:
    return claim_task(task_id)


def run_delete_task(task_id: str) -> str:
    return delete_task(task_id)


# 定义调度定时任务函数
def run_schedule_cron(
    cron: str,  # cron表达式,
    prompt: str,  # 提示词,
    recurring: bool = True,  # 是否循环,
    durable: bool = True,  # 是否持久化
) -> str:
    # 调用schedule_job 安排定时任务 返回结果
    result = schedule_job(cron, prompt, recurring, durable)
    # 如果是字符串 表示出错
    if isinstance(result, str):
        # 返回错误提示
        return f"错误: {result}"
    # 返回调度成功信息 包裹id 表达式和prompt
    return f"已调度 {result.id}: '{cron}' ->{prompt}"


# 定义列出所有 cron定时任务的函数
def run_list_crons() -> str:
    # 使用锁确保并发安全 读取所有 scheduled_jobs
    with cron_lock:
        jobs = list(scheduled_jobs.values())
    # 如果没有任何任务 返回空提示
    if not jobs:
        return "暂无 cron 任务。 使用schedule_cron添加"
    # 初始化结果字符串列表
    lines = []
    # 遍历所有定时任务
    for j in jobs:
        # 根据 recurring 标记区分“循环”或“单次”
        tag = "循环" if j.recurring else "单次"
        # 根据 durable 标记区分“持久化”或“会话”
        dur = "持久化" if j.durable else "会话"
        # 拼接任务的信息字符串并加入列表
        lines.append(f"  {j.id}: '{j.cron}' → {j.prompt[:40]} [{tag}, {dur}]")
    # 返回所有任务拼接后的字符串
    return "\n".join(lines)


# 定义取消定时任务的函数
def run_cancel_cron(job_id: str) -> str:
    # 调用 cancel_job 并返回结果
    return cancel_job(job_id)


# 定义取消定时任务的函数
def run_spawn_teammate(name: str, role: str, prompt: str) -> str:
    # 调用 spawn_teammate_thread 启动队友 agent，传递名字、角色和 prompt
    return spawn_teammate_thread(name, role, prompt)


# 定义函数 启动一个队友agent线程
def run_send_message(to: str, content: str) -> str:
    # 发送方固定为当前会话身份 不可伪造
    from_agent = current_agent.get()
    # 使用BUS发送消息
    BUS.send(from_agent, to, content)
    print(f"已从 {from_agent} 发送给 {to}")
    if to != LEAD_NAME and not is_teammate_running(to):
        # 返回已写入收件箱但队友未运行的提示
        return f"已从{from_agent} 写入{to} 的收件箱, 但该队友未在运行 , 请spawn_teammate 重启后才会被读取"
    # 返回发送结果的字符说明
    return f"已从 {from_agent} 发送给 {to}"


# 定义函数 仅允许当前Agent 自己的收件箱(Lead 只能读 lead)
def run_check_inbox() -> str:
    # 当前会话身份
    name = current_agent.get()
    # Lead 与队友都只能消费自己的收件箱 避免抢走对方消息
    msgs = consume_inbox(name)
    # 如果收件箱为空 返回提示信息
    if not msgs:
        return f" ({name} 的收件箱为空)"
    return format_inbox_messages(msgs)


def run_await_teammates(
    names: list[str] | None = None, timeout: float | None = None
) -> str:
    """阻塞等待队友 result；仅 Lead 应调用。"""
    if current_agent.get() != LEAD_NAME:
        return "错误：仅 lead 可调用 await_teammates"
    return wait_for_teammates(names=names, timeout=timeout)


# 定义 TOOL_HANDLERS字典 , 将‘bash’ 设置为'run_bash'函数
TOOL_HANDLERS = {
    "bash": run_bash,  # 执行shell命令
    "read_file": run_read,  # 读取文件内容
    "write_file": run_write,  # 写入文件内容
    "edit_file": run_edit,  # 编辑文件内容
    "glob": run_glob,  # 通配符路径匹配
    "todo_write": run_todo_write,  # 创建并管理当前编码会话的任务列表
    "load_skill": load_skill,  # 按名称加载技能的完整内容
    "create_task": run_create_task,  # 创建新任务
    "list_tasks": run_list_tasks,
    "get_task": run_get_task,  # 按 ID 获取任务完整详情
    "claim_task": run_claim_task,  # 认领 pending 任务，设置 owner 并改为 in_progress
    "complete_task": run_complete_task,  # 完成 in_progress 任务，并报告下游解阻任务
    "delete_task": run_delete_task,  # 删除任务
    "schedule_cron": run_schedule_cron,  # 创建调度定时任务
    "list_crons": run_list_crons,  # 列出所有定时任务
    "cancel_cron": run_cancel_cron,  # 取消定时任务
    "spawn_teammate": run_spawn_teammate,  # 在后台线程启动队友 Agent。
    "send_message": run_send_message,  # 通过 MessageBus 向队友发送消息
    "check_inbox": run_check_inbox,  # 仅检查当前Agent 自己的收件箱
    "await_teammates": run_await_teammates,  # 阻塞等待队友 result。
    "request_shutdown": run_request_shutdown,  # 请求队友优雅关闭
    "request_plan": run_request_plan,  # 要求队友提交计划供审核
    "submit_plan": run_submit_plan,  # 向Lead提交计划待审批
    "review_plan": run_review_plan,  # 按request_id 批准或拒绝已提交的计划
    "create_worktree": run_create_worktree,  # 创建隔离 git worktree
    "remove_worktree": run_remove_worktree,  # 删除 worktree
    "keep_worktree": run_keep_worktree,  # 保留 worktree 供审查
    "connect_mcp": run_connect_mcp,  # 连接 MCP 服务器并发现外部工具
}
