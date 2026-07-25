# 从config模块中导入WORKDIR变量
from config import WORKDIR

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

# 三道门进串联 执行前依次检查每一个关卡


def check_permission(tool_name: str, args: dict) -> bool:
    # 如果工具名称是bash，则检查命令是否在禁止列表中，如果是，则返回False
    if tool_name == "bash":
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
                print(f"\033[93m[!] 实际调用: {tool_name} {args}\033[0m")
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
    elif tool_name in ["write_file", "edit_file"]:
        # 获取文件路径参数
        path = args.get("path", "")
        # 如果不在工作区内 提示警告
        print(f"\033[91m[!] 检查路径: {path}\033[0m")
        # 显示尝试的操作的工具以及参数
        print(f"\033[91m[!] 实际调用: {tool_name} {args}\033[0m")
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
