# 导入json模块用于处理JSON数据
# 导入json模块用于处理JSON数据
import json
import random

# 导入time模块用于获取当前时间戳
import time

# 从dataclasses模块导入dataclass和asdict用于数据结构定义和转换
from dataclasses import asdict, dataclass

# 从config.py 模块导入任务目录和文本编码设置
from config import TASKS_DIR, TEXT_ENCODING


# 定义一个名为Task的类
@dataclass
class Task:
    # 任务ID
    id: str
    # 任务主题
    subject: str
    # 任务描述
    description: str
    # 任务状态
    status: str
    # 任务负责人
    owner: str | None
    # 任务依赖列表
    blockedBy: list[str]


# 获取所有任务列表
def list_tasks() -> list[Task]:
    return [
        # 读取每个任务文件并转为Task对象
        Task(**json.loads(p.read_text(encoding=TEXT_ENCODING)))
        # 查找所有任务json文件 并排序
        for p in sorted(TASKS_DIR.glob("task_*.json"))
    ]


# 加载指定ID的任务 返回的是类的实例
def load_task(task_id: str) -> Task:
    return Task(**json.loads(_task_path(task_id).read_text(encoding=TEXT_ENCODING)))


# 获取指定任务的JSON字符串
def get_task(task_id: str) -> str:
    return json.dumps(asdict(load_task(task_id)), indent=2, ensure_ascii=False)


# 判断任务是否可以开始
def can_start(task_id: str) -> bool:
    # 加载当前任务消息
    task = load_task(task_id)
    # 遍历所有依赖任务
    for dep_id in task.blockedBy:
        # 依赖任务文件不存在则不可开始
        if not _task_path(dep_id).exists():
            return False
        # 依赖任务未完成也不可开始
        if load_task(dep_id).status != "completed":
            return False
    # 所有依赖都满足
    return True


# 根据任务ID生成任务文件路径
def _task_path(task_id: str):
    return TASKS_DIR / f"{task_id}.json"


# 保存Task对象到文件
def save_task(task: Task):
    _task_path(task.id).write_text(
        json.dumps(asdict(task), indent=2, ensure_ascii=False), encoding=TEXT_ENCODING
    )


# 创建一个新任务并且保存
def create_task(
    subject: str, description: str = "", blockedBy: list[str] | None = None
) -> Task:
    task = Task(
        # 生成唯一的任务ID
        id=f"task_{int(time.time())}_{random.randint(0, 9999):04d}",
        # 设置任务主题
        subject=subject,
        # 设置任务描述
        description=description,
        # 任务初始状态为Pending
        status="pending",
        # 出事负责人为空
        owner=None,
        # 设置依赖列表 为空则默认[]
        blockedBy=blockedBy or [],
    )
    # 存储任务到文件
    save_task(task)
    return task


# 认领任务
def claim_task(task_id: str, owner: str = "agent") -> str:
    # 加载任务
    task = load_task(task_id)
    # 如果任务状态不是pending 则无法认领
    if task.status != "pending":
        return f"任务 {task_id} 状态为 {task.status} , 无法认领"
    # 如果任务被依赖阻塞 则无法认领
    if not can_start(task_id):
        # 找出所有未完成的依赖
        deps = [
            d
            for d in task.blockedBy
            if not _task_path(d).exists() or load_task(d).status != "completed"
        ]
        return f"被阻塞，依赖: {deps}"
    # 设置负责人
    task.owner = owner
    # 设置任务状态为进行中
    task.status = "in_progress"
    # 保存任务 更新任务状态
    save_task(task)
    # 在控制台输出认领提示
    print(f"  \x1b[36m[认领] {task.subject} → in_progress（负责人: {owner}）\x1b[0m")
    # 返回认领结果字符串
    return f"已认领 {task.id}（{task.subject}）"


# 完成任务
def complete_task(task_id: str) -> str:
    # 加载任务
    task = load_task(task_id)
    # 如果任务不是进行中的状态 则无法完成
    if task.status != "in_progress":
        return f"任务 {task_id} 状态为 {task.status}, 无法完成"
    # 设置任务状态为已完成
    task.status = "completed"
    # 保存任务 更新任务状态
    save_task(task)
    # 查找因本任务解锁 现在可以开始的所有等待任务
    unblocked = [
        t.subject
        for t in list_tasks()
        # if t.status == "pending" and task_id in t.blockedBy and can_start(t.id)
        if t.status == "pending" and t.blockedBy and can_start(t.id)
    ]
    # 在控制台输出任务完成信息
    print(f"  \x1b[32m[完成] {task.subject} ✓\x1b[0m")
    # 构造返回信息
    msg = f"已完成 {task.id}（{task.subject}）"
    # 如果有已解锁的任务，则信息中增加这些任务
    if unblocked:
        msg += f"\n已解阻: {', '.join(unblocked)}"
        print(f"  \x1b[33m[解阻] {', '.join(unblocked)}\x1b[0m")
    # 返回最终的信息
    return msg


# 删除任务
def delete_task(task_id):
    task_path = _task_path(task_id)
    if not task_path.exists():
        return f"任务{task_id}不存在 无法删除"
    task = load_task(task_id)
    # 获取依赖项
    dependents = []
    for t in list_tasks():
        if task_id in t.blockedBy:
            dependents.append(t)
    # 如果有依赖任务 则判断是否可以删除
    if dependents:
        incompleted_deps = [t for t in dependents if t.status != "completed"]
        if incompleted_deps:
            dep_info = " , ".join([f"{t.id}({t.subject})" for t in incompleted_deps])
            return f"任务{task_id}被 依赖切未完成, 无法删除, 依赖的依赖:{dep_info}"
        print(f"[提醒] 任务{task_id}被已经完成的任务依赖，将清理依赖关系")
        # 删除任务 task_id 前，把其他已完成任务中对它的依赖记录移除，避免删除后留下一个指向不存在任务的依赖。
        for t in dependents:
            t.blockedBy = [d for d in t.blockedBy if d != task_id]
            save_task(t)
            print(f"- 已经清理了{t.id}依赖")
    # 删除文件
    task_path.unlink()
    msg = f"已经删除任务{task_id}({task.subject})"
    print(msg)
    return msg
