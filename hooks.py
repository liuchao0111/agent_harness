#  从config模块导入工作目录变量WORKDIR
from config import WORKDIR

# 定义一个钩子字典,每个事件对应一个函数列表,用于在事件发生时调用这些函数
HOOKS = {"UserPromptSubmit": [], "PreToolUse": [], "PostToolUse": [], "Stop": []}

# 定义禁止执行的命令列表

DENY_LIST = [
    "rm -rf /",
    "sudo",
    "shutdown",
    "reboot",
    "> /dev/",
    "mkfs",
    "dd if=",
]

# 定义用户需要确认的命令列表
DESTRUCTIVE = ["rm", "> /etc/", "chmod 777", "del", "erase"]


# 注册钩子函数 将回调添加到对应的事件钩子列表
def register_hook(event: str, callback):
    HOOKS[event].append(callback)


# 注入当前工作目录信息到用户查询
def workspace_inject_hook(query: str) -> str | None:
    # 打印注入工作目录的钩子信息
    print(f"\x1b[90m[HOOK] UserPromptSubmit：注入工作目录 {WORKDIR}\x1b[0m")
    # 返回带有工作目录信息的查询字符串
    return f"<workspace>\n当前工作目录：{WORKDIR}\n</workspace>\n\n{query}"


# 权限控制钩子函数 对命令执行进行校验
def permission_hook(name: str, args: dict) -> bool:
    # 如果工具名称是bash，则检查命令是否在禁止列表中，如果是，则返回False
    if name == "bash":
        # 遍历每一条禁止执行的命令模式
        for pattern in DENY_LIST:
            # 如果命令行参数中包含禁止模式
            if pattern in args.get("command", ""):
                # 打印红色警告信息 显示拦截内容
                print(f"\033[91m[!] 拦截危险命令: {args.get('command', '')}\033[0m")
                # 返回表示不允许执行
                return "禁止列表拒绝权限"

        # 遍历每一条危险关键字
        for kw in DESTRUCTIVE:
            # 如果命令行参数中包含危险关键字
            if kw in args.get("command", ""):
                # 打印黄色警告信息 显示危险关键字
                print(f"\033[93m[!] 危险关键字: {kw}\033[0m")
                # 显示实际调用的工具和参数
                print(f"\033[93m[!] 实际调用: {name} {args}\033[0m")
                # 提示用户是否继续执行 输入yes或者y才继续
                choice = (
                    input(
                        "\033[93m[!] 该命令可能会破坏系统,是否继续执行? (yes/y继续, 其他取消): \033[0m"
                    )
                    .strip()
                    .lower()
                )
                # 如果用户输入不是yes或者y，则返回False
                if choice not in ["yes", "y"]:
                    print("\033[93m[!] 已取消执行\033[0m")
                    return "用户拒绝执行"
    # 如果工具名称为write_file或者edit_file，则检查路径是否在工作目录之外，如果是，则返回False
    elif name in ["write_file", "edit_file"]:
        # 获取文件路径参数
        path = args.get("path", "")
        # 如果不在工作区内 提示警告
        print(f"\033[91m[!] 检查路径: {path}\033[0m")
        # 显示尝试的操作的工具以及参数
        print(f"\033[91m[!] 实际调用: {name} {args}\033[0m")
        # 如果路径不在工作目录下，则打印红色警告信息 并返回False
        if not (WORKDIR / path).resolve().is_relative_to(WORKDIR.resolve()):
            # 询问用户是否允许继续执行 输入yes或者y才继续
            choice = (
                input(
                    "\033[91m[!] 该路径不在工作目录内,是否继续执行? (yes/y继续, 其他取消): \033[0m"
                )
                .strip()
                .lower()
            )
            # 如果用户输入不是yes或者y，则返回False
            if choice not in ["yes", "y"]:
                # 返回用户拒绝权限
                return "用户拒绝权限，路径不在工作目录内"


# 日志钩子函数 记录调用信息
def log_hook(name: str, args: dict):
    # 取参数前两项并转换为字符串用于预览
    args_preview = str(list(args.values())[:2])[:60]
    # 打印钩子触发信息
    print(f"\x1b[90m[HOOK] {name}({args_preview})\x1b[0m")
    # 无特殊行为 直接返回None
    return None


# 钩子、处理工具输出过大的情况
def large_output_hook(name: str, args: dict, output):
    # 判断输出长度是否超过10w字符
    if len(str(output)) > 100000:
        # 打印输出过大警告
        print(f"\x1b[33m[HOOK] ⚠ {name} 输出过大：{len(str(output))} 字符\x1b[0m")
    # 返回None
    return None


# 会话统计钩子函数
def summary_hook(messages: list):
    # 统计工具调用的次数
    tool_count = sum(1 for m in messages if m.get("role") == "tool")
    # 打印工具调用信息
    print(f"\x1b[90m[HOOK] Stop：本次会话共使用 {tool_count} 次工具调用\x1b[0m")
    # 无特殊返回，直接None
    return None


# 注册用户提交的事件钩子函数
register_hook("UserPromptSubmit", workspace_inject_hook)
# 注册工具使用前权限检查钩子
register_hook("PreToolUse", permission_hook)
# 注册工具使用前日志记录钩子
register_hook("PreToolUse", log_hook)
# 注册工具使用后大输出检测钩子
register_hook("PostToolUse", large_output_hook)
# 注册停止事件的会话总结钩子
register_hook("Stop", summary_hook)


# 触发用户输入相关的钩子链
def trigger_user_prompt_hooks(query: str) -> str:
    # 当前待处理的查询
    current = query
    # 依次触发钩子
    for callback in HOOKS["UserPromptSubmit"]:
        # 调用每个钩子获取结果
        result = callback(current)
        # 如果返回字符串则更新current
        if isinstance(result, str):
            current = result
    # 返回处理后的查询
    return current


# 通用钩子触发函数
def trigger_hooks(event: str, *args):
    # 按注册顺序依次触发对应事件下的钩子
    for callback in HOOKS[event]:
        # 调用钩子并获取返回值
        result = callback(*args)
        # 如果返回非None则终止并返回
        if result is not None:
            return result
    # 所有钩子都返回None则返回None
    return None
