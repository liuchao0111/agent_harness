import glob as g

# 导入os模块 用于与操作系统交互
import os

# 导入subprocess模块 用于执行子进程
import subprocess

# 从config模块导入TEXT_ENCODING和WORKDIR，用于指定文本编码和工作目录
from config import TEXT_ENCODING, WORKDIR

# 从utils模块中导入decode_subprocess_output函数 用于解码子进程输出
from utils import decode_subprocess_output, safe_path


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
def run_read(path: str, limit: int | None = None) -> str:
    # 尝试执行以下代码
    try:
        # 使用safe_path校验并控制文件路径,按指定编码读取内容并按行分割
        lines = safe_path(path).read_text(encoding=TEXT_ENCODING).splitlines()
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
def run_write(path: str, content: str) -> str:
    # 尝试执行以下代码
    try:
        # 使用safe_path校验并获取目标文件路径
        file_path = safe_path(path)
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
def run_edit(path: str, old_text: str, new_text: str) -> str:
    # 尝试执行以下代码
    try:
        # 使用safe_path校验并获取目标文件路径
        file_path = safe_path(path)
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
def run_glob(pattern: str) -> str:
    # 尝试执行以下代码
    try:
        # 初始化结果列表
        results = []
        # 遍历所有匹配到的路径 根目录为WORKDIR
        for match in g.glob(pattern, root_dir=WORKDIR):
            # 检测匹配到的路径是否相对WORKDIR安全
            if (WORKDIR / match).resolve().is_relative_to(WORKDIR):
                # 将安全的匹配结果加入结果列表
                results.append(match)
        # 如果结果非空 , 拼接为字符串返回 ，否则无法返回无匹配的提示
        return "\n".join(results) if results else "（无匹配"
    except (OSError, PermissionError) as e:
        return f"错误: {e}"


# 定义全局变量CURRENT_TODOS，用于存储当前的任务列表 ，类型为list[dict]
CURRENT_TODOS: list[dict] = []


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


# 定义 TOOL_HANDLERS字典 , 将‘bash’ 设置为'run_bash'函数
TOOL_HANDLERS = {
    "bash": run_bash,
    "read_file": run_read,
    "write_file": run_write,
    "eidt_file": run_edit,
    "glob_file": run_glob,
    "todo_write": run_todo_write,
}
