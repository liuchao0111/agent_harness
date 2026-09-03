# 从config中导入client对象
import random
import time

from openai import APIStatusError, RateLimitError

from config import (
    BASE_DELAY_MS,
    FALLBACK_MODEL,
    MAX_CONSECUTIVE_529,
    MAX_RETRIES,
    MODEL_ID,
    client,
)
from tools.schema import TOOLS


# 定义call_llm函数 参数包括system(系统消息)、message(消息列表)、max_tokens(最大token数)、model(模型名)
def call_llm(system: str, messages: list, max_tokens: int, model: str, tools=None):
    # 调用client.chat.completions.create方法生成响应，传入模型名、拼接的消息、工具集合和最大token数
    return client.chat.completions.create(
        model=model,
        # 将系统提示和传入的消息列表组合成messages参数
        messages=[{"role": "system", "content": system}, *messages],
        tools=tools if tools is not None else TOOLS,
        # 传入最大允许的token数
        max_tokens=max_tokens,
    )


# 定义一个函数，用于判断异常是否为提示过长相关错误
def is_prompt_too_long_error(e: Exception) -> bool:
    # 将异常对象转换为字符串，并转换为小写
    msg = str(e).lower()
    # 返回一个布尔值，判断是否包含与“提示过长”相关的各种关键字
    return (
        # 检查字符串中是否有 'prompt' 且有 'long'
        ("prompt" in msg and "long" in msg)
        # 检查是否有 'prompt_is_too_long'
        or "prompt_is_too_long" in msg
        # 检查是否有 'context_length_exceeded'
        or "context_length_exceeded" in msg
        # 检查是否有 'max_context_window'
        or "max_context_window" in msg
        # 检查是否有 'context_length'
        or "context_length" in msg
        # 检查是否有 'maximum context'
        or "maximum context" in msg
    )


# 定义一个RecoveryState类 用于表示恢复状态
class RecoveryState:
    # 初始化方法
    def __init__(self):
        # 标记是否已升级处理
        self.has_escalated = False
        # 恢复尝试的次数计数
        self.recovery_count = 0
        # 连续发生529错误的计数
        self.consecutive_529 = 0
        # 是否已尝试被动压缩
        self.has_attempted_reactive_compact = False
        # 当前使用模型
        self.current_model = MODEL_ID


# 计算是否是速率限制错误
def _is_rate_limit_error(e: Exception) -> bool:
    # 如果是异常 RateLimitError 类型
    if isinstance(e, RateLimitError):
        # 返回True
        return True
    # 将异常信息转为小写字符串
    msg = str(e).lower()
    # 获取异常类型的名字并转为小写
    name = type(e).__name__.lower()
    # 检查异常类型名字中是否包含 'ratelimit' 或异常信息中是否包含'429'
    return "ratelimit" in name or "429" in msg


def is_overloaded(e: Exception) -> bool:
    # 如果异常是 APIStatusError 并且状态码为 529
    if isinstance(e, APIStatusError) and e.status_code == 529:
        # 返回 True
        return True
    # 将异常信息转为小写字符串
    msg = str(e).lower()
    # 获取异常类型的名字并转为小写
    name = type(e).__name__.lower()
    # 检查异常类型名字中是否包含 'ratelimit' 或异常信息中是否包含'429'
    return "ratelimit" in name or "529" in msg


# 计算重试的延时
def retry_delay(attempt: int, retry_after=None) -> float:
    # 如果有retry_after参数
    if retry_after:
        try:
            #  尝试将 retry_after 转为float 并返回
            return float(retry_after)
        # 如果转换失败则忽略错误
        except TypeError, ValueError:
            pass
    # 计算基础延时 指数退避 最大不超过32000毫秒 并转为秒
    base = min(BASE_DELAY_MS * 2**attempt, 32000) / 1000
    return base + random.uniform(0, base * 0.25)


# 为一个函数增加重试机制
def with_retry(fn, state: RecoveryState):
    # 尝试MAX_RETRIES次
    for attempt in range(MAX_RETRIES):
        try:
            # 执行传入的函数
            result = fn()
            # 529 次数清零
            state.consecutive_529 = 0
            # 返回结果
            return result
            # 捕获所有异常
        except (APIStatusError, RateLimitError) as e:
            # 如果是速率限制错误
            if _is_rate_limit_error(e):
                # 计算重试等待时间
                delay = retry_delay(attempt)
                # 打印重试信息（黄色）
                print(
                    f"  \x1b[33m[429 速率限制] 重试 {attempt + 1}/{MAX_RETRIES}，等待 {delay:.1f}s\x1b[0m"
                )
                # 等待 delay 秒
                time.sleep(delay)
                # 继续下一次重试
                continue
            # 如果是过载错误
            if is_overloaded(e):
                # 529次数加1
                state.consecutive_529 += 1
                # 如果连续529次数 超过最大允许次数
                if state.consecutive_529 >= MAX_CONSECUTIVE_529:
                    # 如果配置了备用模型
                    if FALLBACK_MODEL:
                        # 切换到备用模型
                        state.current_model = FALLBACK_MODEL
                        # 529计算清零
                        state.consecutive_529 = 0
                        # 打印切换模型信息（红色）
                        print(
                            f"  \x1b[31m[529 x{MAX_CONSECUTIVE_529}] 切换到 {FALLBACK_MODEL}\x1b[0m"
                        )
                    # 如果没有备用模型
                    else:
                        # 529 计算请零
                        state.consecutive_529 = 0
                        # 打印未配置备用模型信息（红色）
                        print(
                            f"  \x1b[31m[529 x{MAX_CONSECUTIVE_529}] 未配置 FALLBACK_MODEL，继续重试\x1b[0m"
                        )
                # 计算重试等待时间
                delay = retry_delay(attempt)
                # 打印过载重试信息（黄色）
                print(
                    f"  \x1b[33m[529 过载] 重试 {attempt + 1}/{MAX_RETRIES}，等待 {delay:.1f}s\x1b[0m"
                )
                # 等待 delay 秒
                time.sleep(delay)
                # 继续下一次重试
                continue
            raise
            # 其他已知API相关异常会在此处理，未知异常应被抛出以便上层处理
        except Exception:
            # 如果不是以上错误则抛出异常
            raise
    # 如果超过最大重试次数，抛出运行时错误
    raise RuntimeError(f"超过最大重试次数（{MAX_RETRIES}）")
