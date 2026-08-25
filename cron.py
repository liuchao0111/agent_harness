# 导入json模块，用于序列化与反序列化
import json

# 导入random模块，用于生成随机id
import random

# 导入threading模块，实现多线程
import threading

# 导入time模块，实现定时相关操作
import time

# 引入dataclasses的asdict和dataclass，用于数据结构定义和转换为字典
from dataclasses import asdict, dataclass

# 导入datetime类，处理时间相关
from datetime import UTC, datetime

from config import DURABLE_PATH, TEXT_ENCODING


# 定义CronJob数据类 表示一个定时任务
@dataclass
class CronJob:
    # 任务ID
    id: str
    # cron表达式
    cron: str
    # 任务触发时的提示内容
    prompt: str
    # 是否为循环任务
    recurring: bool
    # 是否需要持久化
    durable: bool


# 定义调度中的任务字典 key为任务id value为CronJob对象
scheduled_jobs: dict[str:CronJob] = {}
# 定义cron执行队列，存储等待消费的 CronJob 对象
cron_queue: list[CronJob] = []

cron_lock = threading.Lock()

# 记录各任务上一次触发时间 key为任务id value为时间字符串
_last_fired: dict[str, str] = {}


# 判断cron表达式中的某个字段和具体时间值是否匹配
def _cron_field_matches(field: str, value: int) -> bool:
    # 如果是通配符*，则总是匹配
    if field == "*":
        return True
    # 支持步进写法，如 */5
    if field.startswith("*/"):
        step = int(field[2:])
        return step > 0 and value % step == 0
    # 多个值逗号分隔，如1,5,10
    if "," in field:
        return any(_cron_field_matches(f.strip(), value) for f in field.split(","))
    # 支持区间写法，如8-10
    if "-" in field:
        lo, hi = field.split("-", 1)
        return int(lo) <= value <= int(hi)
    # 普通数字匹配
    return value == int(field)


# 检查给定时间dt是否满足cron表达式cron_expr
def cron_matches(cron_expr: str, dt: datetime) -> bool:
    # 将cron表达式去除两端空白后按空格分割为字段列表
    fields = cron_expr.strip().split()
    # 如果字段数不是5 则返回False
    if len(fields) != 5:
        return False
    # 解包含5个字段 分别为 分 时 日 月 星期
    minute_field, hour_field, day_of_month_field, month_field, day_of_week_field = (
        fields
    )
    # 计算符合cron语法的星期数字：Python中weekday()，0代表周一，转换为cron的0-6，0为周日
    day_of_week_val = (dt.weekday() + 1) % 7

    # 检查分钟字段是否匹配当前时间的分钟值
    minute_match = _cron_field_matches(minute_field, dt.minute)
    # 检查小时字段是否匹配当前时间的小时值
    hour_match = _cron_field_matches(hour_field, dt.hour)
    # 检查日期（一个月中的某天）字段是否匹配当前日期
    day_of_month_match = _cron_field_matches(day_of_month_field, dt.day)
    # 检查月份字段是否匹配当前月份
    month_match = _cron_field_matches(month_field, dt.month)
    # 检查星期字段是否匹配当前星期数字
    day_of_week_match = _cron_field_matches(day_of_week_field, day_of_week_val)

    # 如果分钟、小时、月份中有任何一个不匹配，直接返回False
    if not (minute_match and hour_match and month_match):
        return False
    # 判断日期字段是否为无约束（即为*号）
    day_of_month_unconstrained = day_of_month_field == "*"
    # 判断星期字段是否为无约束（即为*号）
    day_of_week_unconstrained = day_of_week_field == "*"
    # 若日期和星期都不受约束，直接认为匹配
    if day_of_month_unconstrained and day_of_week_unconstrained:
        return True
    # 如果日期不受约束，只要星期字段匹配则返回True
    if day_of_month_unconstrained:
        return day_of_week_match
    # 如果星期不受约束，只要日期字段匹配则返回True
    if day_of_week_unconstrained:
        return day_of_month_match
    # 否则，只要日期或星期有一个匹配就返回True
    return day_of_month_match or day_of_week_match


# 检查某个cron字段是否合法
def _validate_cron_field(field: str, low: int, high: int) -> str | None:
    # 若字段为 * 合法
    if field == "*":
        return None
    # 检查步长写法
    if field.startswith("*/"):
        step_str = field[2:]
        # 如果不是整数 则不合法
        if not step_str.isdigit():
            return f"无效步长: {field}"
        if int(step_str) <= 0:
            return f"步长必须 > 0: {field}"
        return None
    # 逗号分割多个字段必须校验
    if "," in field:
        for part in field.split(","):
            err = _validate_cron_field(part.strip(), low, high)
            if err:
                return err
        return None
    # 检查区间写法是否合法
    if "-" in field:
        parts = field.split("-", 1)
        if not parts[0].isdigit() or not parts[1].isdigit():
            return f"无效范围: {field}"
        a, b = int(parts[0], int(parts[1]))
        if a < low or a > high or b < low or b > high:
            return f"范围{field} 超出 [{low}-{high}]"
        if a > b:
            return f"范围起始 > 结束: {field}"
        return None
    # 检查是否合法是合法数字
    if not field.isdigit():
        return f"无效字段: {field}"
    val = int(field)
    # 检查数字是否在合法范围
    if val < low or val > high:
        return f"值 {val} 超出 [{low}-{high}]"
    return None


# 校验整个cron表达式是否合法
def validate_cron(cron_expr: str) -> str | None:
    # 拆分cron表达式为字段
    fields = cron_expr.strip().split()
    # 字段书必须为5
    if len(fields) != 5:
        return f"需要 5 个 字段, 实际 {len(fields)} 个"
    # 各字段的上下界
    bounds = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 6)]
    # 字段名称
    names = ["分", "时", "日", "月", "周"]
    # 对每一个字段进行逐一校验
    for field, (low, high), name in zip(fields, bounds, names):
        err = _validate_cron_field(field, low, high)
        if err:
            return f"{name}: {err}"
    return None


# 保存持久化任务到硬盘
def save_durable_jobs():
    # 只保存标记了durable的任务
    durable = [asdict(j) for j in scheduled_jobs.values() if j.durable]
    # 写入到指定任务
    DURABLE_PATH.write_text(
        json.dumps(durable, indent=2, ensure_ascii=False), encoding=TEXT_ENCODING
    )


# 从硬盘加载持久化任务
def load_durable_jobs():
    # 若路径不存在则返回
    if not DURABLE_PATH.exists():
        return
    try:
        # 读取文件 反序列化为对象列表
        jobs = json.loads(DURABLE_PATH.read_text(encoding=TEXT_ENCODING))
        # 每个任务逐一检查合法性 并加入调度列表
        for j in jobs:
            job = CronJob(**j)
            err = validate_cron(job.cron)
            if err:
                print(f"  \x1b[31m[cron] 跳过无效任务 {job.id}: {err}\x1b[0m")
                continue
            scheduled_jobs[job.id] = job
        # 统计有效任务数并打印加载成功提示
        valid = [j for j in jobs if j["id"] in scheduled_jobs]
        if valid:
            print(f"  \x1b[35m[cron] 已加载 {len(valid)} 个持久化任务\x1b[0m")
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as e:
        print(f"  \x1b[31m[cron] 读取持久化任务失败: {e}\x1b[0m")


# 创建调度新任务
def schedule_job(
    cron: str,  # cron表达式
    prompt: str,  # 提示词
    recurring: bool = True,  # 是否循环
    durable: bool = True,  # 是否持久化
) -> CronJob | str:  # 返回CronJob对象或错误字符串
    # 校验cron表达式合法性
    err = validate_cron(cron)
    # 如果校验失败 返回错误字符串
    if err:
        return err
    # 创建CronJob对象 分配随机ID
    job = CronJob(
        id=f"cron_{random.randint(0, 999999):06d}",  # 任务id
        cron=cron,  # cron表达式
        prompt=prompt,  # 提示词
        recurring=recurring,  # 是否循环
        durable=durable,  # 是否持久化
    )
    # 写入任务池 (线程安全)
    with cron_lock:
        scheduled_jobs[job.id] = job
    # 若需持久化 写入硬盘
    if durable:
        save_durable_jobs()
    # 打印调度注册提示
    print(f"  \x1b[35m[cron 注册] {job.id} '{cron}' → {prompt[:40]}\x1b[0m")
    return job


# cron调度主循环(线程内) 添加调度任务到任务队列
def cron_scheduler_loop():
    while True:
        # 每秒调度一次
        time.sleep(1)
        # 获取当前时间
        now = datetime.now(UTC).astimezone()
        # 获取分钟粒度的时间戳标识
        minute_marker = now.strftime("%Y-%m-%d %H:%M")
        # 锁定后穷举所有调度任务
        with cron_lock:
            for job in list(scheduled_jobs.values()):
                try:
                    # 检测当前时间是否符合cron表达式
                    if (
                        cron_matches(job.cron, now)
                        and _last_fired.get(job.id) != minute_marker
                    ):
                        # 上一次调度和这次的minute不相等才能触发
                        # 将任务加入待触发队列
                        cron_queue.append(job)
                        # 记录本次触发
                        _last_fired[job.id] = minute_marker
                        # 打印触发提示
                        print(
                            f"  \x1b[35m[cron 触发] {job.id} → {job.prompt[:40]}\x1b[0m"
                        )
                    #  若任务不需要循环 触发一次则移除
                    if not job.recurring:
                        scheduled_jobs.pop(job.id)
                        # 若需要持久化 移除后保存
                        if job.recurring:
                            save_durable_jobs()
                except (ValueError, KeyError, TypeError, AttributeError) as e:
                    # 若出错，打印异常日志
                    print(f"  \x1b[31m[cron 错误] {job.id}: {e}\x1b[0m")


# 判断是否有等待消费的任务
def has_cron_queue() -> bool:
    with cron_lock:
        return bool(cron_queue)


# 启动cron调度器(新线程)
def start_cron_scheduler():
    # 先加载持久化任务
    load_durable_jobs()
    # 启动调度线程
    threading.Thread(target=cron_scheduler_loop, daemon=True).start()
    # 打印提示
    print("\x1b[35m[cron] 调度线程已启动\x1b[0m'")


# 消费定时任务
def consume_cron_queue() -> list[CronJob]:
    with cron_lock:
        jobs = cron_queue.copy()
        cron_queue.clear()
    return jobs


# 取消一个任务
def cancel_job(job_id: str) -> str:
    # 从任务池移除该任务
    with cron_lock:
        job = scheduled_jobs.pop(job_id, None)
        # 若找不到则返回提示
        if not job:
            return f"未找到任务 {job_id}"
        # 若该任务需要持久化存盘
        if job.durable:
            save_durable_jobs()
        # 打印取消提示
        print(f"  \x1b[31m[cron 取消] {job_id}\x1b[0m")
        return f"已取消 {job_id}"


# 定义队列处理器主循环数 参数为调度函数和agent互斥锁
def _queue_processor_loop(dispatch_fn, agent_lock):
    while True:
        # 等待0.2 秒后 再处理 降低 CPU占用
        time.sleep(0.2)
        # 如果没有可消费的定时任务队列 跳过本次循环
        if not has_cron_queue():
            continue
        # 未能获得agent锁 则跳过本次循环
        if not agent_lock.acquire(blocking=False):
            continue
        try:
            # 再次检测是否真的有可消费的定时任务队列
            if not has_cron_queue():
                continue
            # 打印处理队列任务的提示信息
            print("\n  \x1b[35m[队列处理器] 投递定时任务\x1b[0m")
            # 执行传入的调度分发函数
            dispatch_fn()
            # 再打印一个空行，便于输出分隔
            print()
        finally:
            # 在任何情况下都释放agent锁
            agent_lock.release()


def start_queue_processor(run_agent_turn_locked, agent_lock):
    # 创建一个新的线程 目标函数为_queuer_processor_loop
    threading.Thread(
        # 指定线程的目标函数
        target=_queue_processor_loop,
        # 传递dispatch_fn 和 agent_lock 作为参数
        args=(run_agent_turn_locked, agent_lock),
        # 启动线程
        daemon=True,
    ).start()
    # 打印队列处理器已启动的提示信息
    print("  \x1b[35m[队列处理器] 已启动\x1b[0m")
