
# worktree 隔离：创建 / 绑定 / 删除 / 保留 / 事件日志
# 引入 json 标准库
import json

# 引入正则表达式库
import re

# 引入子进程库，用于执行外部命令
import subprocess

# 引入时间模块
import time

# 引入 Path 对象用于文件路径操作
from pathlib import Path

# 从 config 模块导入主目录、worktree 目录、文本编码
from config import TEXT_ENCODING, WORKDIR, WORKTREES_DIR

# 从 tasks 模块导入任务的载入与保存函数
from tasks import load_task, save_task

# 合法 worktree 名称的正则表达式：只允许字母、数字、点、下划线、连字符，长度 1 到 64
VALID_WT_NAME = re.compile(r'^[A-Za-z0-9._-]{1,64}$')
# 定义校验 worktree 名称的函数，类型提示：输入字符串，返回字符串或 None
def validate_worktree_name(name: str) -> str | None:
    # 校验名称；合法返回 None，非法返回错误信息。
    """校验名称；合法返回 None，非法返回错误信息。"""
    # 如果名称为空，返回错误信息
    if not name:
        return 'worktree 名称不能为空'
    # 如果名称为 . 或 ..，不是有效名称
    if name in ('.', '..'):
        return f"'{name}' 不是有效的 worktree 名称"
    # 如果名称不符合正则表达式，返回格式说明
    if not VALID_WT_NAME.match(name):
        return (
            f"无效的 worktree 名称 '{name}'："
            '仅允许字母、数字、点、下划线、连字符（1-64 字符）'
        )
    # 合法则返回 None
    return None

# 定义运行 git 命令的函数，返回(是否成功，输出内容)元组
def run_git(args: list[str]) -> tuple[bool, str]:
    # 在主仓库执行 git 命令，返回 (成功, 输出)。
    """在主仓库执行 git 命令，返回 (成功, 输出)。"""
    # 捕获异常处理超时
    try:
        # 执行 git 命令，设置当前目录、捕获输出、超时30秒
        r = subprocess.run(
            ['git'] + args,
            check=False, cwd=WORKDIR,
            capture_output=True,
            timeout=30,
        )
        # 延迟导入工具模块的解码函数
        from utils import decode_subprocess_output
        # 解码输出并合并 stdout 和 stderr，去除两侧空白
        out = decode_subprocess_output((r.stdout or b'') + (r.stderr or b'')).strip()
        # 最多截取前 5000 个字符，否则返回（无输出）
        out = out[:5000] if out else '（无输出）'
        # 返回命令是否成功及输出
        return r.returncode == 0, out
    # 捕获超时异常，返回失败和对应错误信息
    except subprocess.TimeoutExpired:
        return False, '错误：git 超时'
# 定义任务绑定到 worktree 的函数
def bind_task_to_worktree(task_id: str, worktree_name: str) -> None:
    # 仅写入 task.worktree，不改变 status（保持 pending）。
    """仅写入 task.worktree，不改变 status（保持 pending）。"""
    # 加载指定任务
    task = load_task(task_id)
    # 设置任务的 worktree 字段
    task.worktree = worktree_name
    # 保存任务
    save_task(task)
    # 打印绑定信息（黄色）
    print(f'  \x1b[33m[绑定] {task.subject} → worktree:{worktree_name}\x1b[0m')
# 定义事件日志写入函数
def log_event(event_type: str, worktree_name: str, task_id: str = '') -> None:
    # 构造事件字典
    event = {
        'type': event_type,
        'worktree': worktree_name,
        'task_id': task_id,
        'ts': time.time(),
    }
    # 定义事件日志文件路径
    events_file = WORKTREES_DIR / 'events.jsonl'
    # 以追加方式打开事件日志文件
    with open(events_file, 'a', encoding=TEXT_ENCODING) as f:
        # 写入 json 序列化的事件，末尾加换行
        f.write(json.dumps(event, ensure_ascii=False) + '\n')

# 定义创建 worktree 的函数，可同时绑定任务
def create_worktree(name: str, task_id: str = '') -> str:
    # 校验 worktree 名称
    err = validate_worktree_name(name)
    # 如果校验不通过，返回错误信息
    if err:
        return f'错误：{err}'
    # 构造 worktree 路径
    path = WORKTREES_DIR / name
    # 如果路径已存在，返回已存在的信息
    if path.exists():
        return f"worktree '{name}' 已存在于 {path}"
    # 使用 git 添加 worktree，带分支名
    ok, result = run_git(['worktree', 'add', str(path), '-b', f'wt/{name}', 'HEAD'])
    # 如果命令失败，返回 git 错误信息
    if not ok:
        return f'Git 错误：{result}'
    # 若有任务，绑定该 worktree
    if task_id:
        bind_task_to_worktree(task_id, name)
    # 记录事件日志
    log_event('create', name, task_id)
    # 打印创建信息（黄色）
    print(f'  \x1b[33m[worktree] 已创建: {name} @ {path}\x1b[0m')
    # 返回已创建的文本结果
    return f"worktree '{name}' 已创建于 {path}"

# 运行创建 worktree 的接口函数
def run_create_worktree(name: str, task_id: str = '') -> str:
    # 调用真正的创建函数
    return create_worktree(name, task_id)


# 定义查询 worktree 修改/未提交状态的函数
def _count_worktree_changes(path: Path) -> tuple[int, int]:
    # 返回 (未提交文件数, 未推送提交数)；失败返回 (-1, -1)。
    """返回 (未提交文件数, 未推送提交数)；失败返回 (-1, -1)。"""
    # 异常捕获处理
    try:
        # 运行 git status 获取未提交文件
        r1 = subprocess.run(
            ['git', 'status', '--porcelain'],
            cwd=path,
            capture_output=True,
            timeout=10,
        )
        # 解码状态输出
        from utils import decode_subprocess_output
        status_out = decode_subprocess_output(r1.stdout).strip()
        # 统计非空的变更行数
        files = len([line for line in status_out.splitlines() if line.strip()])
        # 运行 git log 查询未推送提交数
        r2 = subprocess.run(
            ['git', 'log', '@{push}..HEAD', '--oneline'],
            cwd=path,
            capture_output=True,
            timeout=10,
        )
        # 解码日志输出
        log_out = decode_subprocess_output(r2.stdout).strip()
        # 统计未推送提交的行数
        commits = len([line for line in log_out.splitlines() if line.strip()])
        # 返回未提交文件数与未推送提交数
        return files, commits
    # 发生异常时返回 -1, -1
    except Exception:
        return -1, -1

# 定义删除 worktree 的函数，支持强制丢弃更改
def remove_worktree(name: str, discard_changes: bool = False) -> str:
    # 校验 worktree 名称
    err = validate_worktree_name(name)
    # 校验不通过返回错误信息
    if err:
        return err
    # 构造 worktree 路径
    path = WORKTREES_DIR / name
    # 路径不存在则提示未找到
    if not path.exists():
        return f"未找到 worktree '{name}'"
    # 若不是强制丢弃，检查状态
    if not discard_changes:
        files, commits = _count_worktree_changes(path)
        # 状态不可用，提示需要强制删除
        if files < 0:
            return (
                f"无法验证 worktree '{name}' 状态。"
                '请设 discard_changes=true 强制删除。'
            )
        # 有未提交或未推送，提示需强制或保留
        if files > 0 or commits > 0:
            return (
                f"worktree '{name}' 有 {files} 个未提交文件、"
                f'{commits} 个未推送提交。'
                '请设 discard_changes=true 强制删除，'
                '或使用 keep_worktree 保留供审查。'
            )
    # 删除 worktree（目录），--force 强制
    ok1, _ = run_git(['worktree', 'remove', str(path), '--force'])
    # 删除失败则返回错误
    if not ok1:
        return f"删除 worktree '{name}' 目录失败"
    # 删除关联分支
    run_git(['branch', '-D', f'wt/{name}'])
    # 记录删除事件
    log_event('remove', name)
    # 打印删除信息（黄色）
    print(f'  \x1b[33m[worktree] 已删除: {name}\x1b[0m')
    # 返回删除结果描述
    return f"worktree '{name}' 已删除"

# 运行删除 worktree 的接口函数
def run_remove_worktree(name: str, discard_changes: bool = False) -> str:
    # 调用真正的删除函数
    return remove_worktree(name, discard_changes)


# 定义保留 worktree 供审查的函数
def keep_worktree(name: str) -> str:
    # 校验 worktree 名称
    err = validate_worktree_name(name)
    # 校验失败返回错误信息
    if err:
        return err
    # 记录保留事件
    log_event('keep', name)
    # 打印保留信息（青色）
    print(f'  \x1b[36m[worktree] 已保留: {name}\x1b[0m')
    # 返回保留结果描述
    return f"worktree '{name}' 已保留供审查（分支: wt/{name}）"

# 运行保留 worktree 的接口函数
def run_keep_worktree(name: str) -> str:
    # 调用真正的保留函数
    return keep_worktree(name)
