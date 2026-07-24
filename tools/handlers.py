# 导入os模块 用于与操作系统交互
import os

# 导入subprocess模块 用于执行子进程
import subprocess

# 从utils模块中导入decode_subprocess_output函数 用于解码子进程输出
from utils import decode_subprocess_output


# 定义run_bash函数,接收一个字符串类型参数command,并返回字符串
def run_bash(command: str) -> str:
    # 如果当前操作系统是Windows系统 并且命令是'date'(忽略前后空白并转位小写)
    if os.name == "nt" and command.strip().lower() == "date":
        # 将命令改为Windows下同时输出日期和时间的命令
        command = "date /t & time /t"
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
            cwd=os.getcwd(),  # 当前工作目录设置为当前路径
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


# 定义 TOOL_HANDLERS字典 , 将‘bash’ 设置为'run_bash'函数
TOOL_HANDLERS = {"bash": run_bash}
