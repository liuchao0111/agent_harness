import threading

from agent import agent_loop

# 从cron模块导入start_cron_scheduler和start_queue_processor函数
from cron import start_cron_scheduler, start_queue_processor

# 导入trigger_user_prompt_hooks函数
from hooks import trigger_user_prompt_hooks

# 定义会话历史记录列表
session_history: list = []

# 定义互斥锁用于线程同步
agent_lock = threading.Lock()


# 定义一个函数 带锁执行agent回合 可选参数为用户输入
def run_agent_turn_locked(user_query: str | None = None):
    # 如果用户有输入 将其加入会话历史中
    if user_query is not None:
        session_history.append({"role": "user", "content": user_query})
    # 启动agent主循环 处理会话
    agent_loop(session_history)
    # 获取最新一条历史记录，如果历史为空则为None
    final = session_history[-1] if session_history else None
    # 如果最新一条是助手且消息内容不为空，则打印出来
    if final and final.get("role") == "assistant" and final.get("content"):
        print(final["content"])


def main():
    print("输入问题，回车发送。输入q 退出。\n")
    # 定时投递/安排任务(产生任务) 作用是启动定时任务调度器。调度器负责定时、周期性的向任务队列投递任务 , 它为整个系统源源不断的按计划产生"待处理事件"
    start_cron_scheduler()
    # “消费/处理任务队列中的实际任务”， 作用是不断轮训检查任务队列，一旦发现有待处理的任务，就会调用agent处理方法完成任务 因此 这个线程是专门用来"实际执行任务"的
    start_queue_processor(run_agent_turn_locked, agent_lock)
    # 进入无限循环,不断接受用户输入
    while True:
        try:
            # 获取用户输入 带有提示符
            query = input("\x1b[36m>> \x1b[0m")
        except EOFError, KeyboardInterrupt:
            # 异常时输出循环
            break
        # 如果输入的内容为空，或者用户输入了q quit exit 空串 都退出循环
        if query.strip().lower() in ("q", "exit", ""):
            break
        # 触发’UserPromptSubmit‘钩子进行前置处理 返回处理后的用户输入
        query = trigger_user_prompt_hooks(query)
        # 上锁 执行agent回合处理
        with agent_lock:
            run_agent_turn_locked(query)
        # 打印换行
        print()


if __name__ == "__main__":
    main()
