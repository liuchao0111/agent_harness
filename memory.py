import json
import re
import time

# 加载与对话相关的记忆内容 拼接为字符串返回
from config import (
    CONSOLIDATE_THRESHOLD,
    MEMORY_DIR,
    MEMORY_INDEX,
    MODEL_ID,
    TEXT_ENCODING,
    client,
)
from utils import llm_text, message_text, parse_frontmatter


# 根据对话内容选择最相关的记忆文件 最多返回max_items个文件名
def select_relevant_memories(messages: list, max_items: int = 5) -> list[str]:
    # 获取所有记忆文件信息
    files = list_memory_files()
    # 如果没有记忆文件 直接返回空列表
    if not files:
        return []
    # 初始化保存最近用户消息内容的列表
    recent_texts = []
    # 逆序遍历消息列表 提取最近三条用户消息
    for msg in reversed(messages):
        if msg.get("role") == "user":
            # 获取消息文本并去除前后空白
            text = message_text(msg).strip()
            # 如果消息文本不为空 则加入recent_texts
            if text:
                recent_texts.append(text)
            # 最多收集三条消息
            if len(recent_texts) >= 3:
                break
    # 将收集到的消息拼接成字符串 并限制最大长度为2000
    recent = " ".join(reversed(recent_texts))[:2000]
    # 如果合成后的消息字符串为空 返回空列表
    if not recent.strip():
        return []
    # 构建记忆目录字符串
    catalog = "\n".join(
        f"{i}: {f['name']} - {f['description']}" for i, f in enumerate(files)
    )
    # 构造用于LLM筛选相关记忆的prompt
    prompt = (
        "根据近期对话和下方记忆目录 选出明显相关的记忆索引。"
        "仅返回 JSON 整数数组 , 例如[0,3]。若无相关则返回[]. \n\n"
        f"近期对话:\n{recent}\n\n记忆目录:\n{catalog}"
    )
    try:
        # 发送消息到LLM 让其分析哪些记忆相关
        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
        )
        # 解析LLM返回的文本内容
        text = llm_text(response)
        # 使用正则表达式匹配JSON数组内容
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                # 将匹配到的字符串解析为Python列表
                indices = json.loads(match.group())
            except json.JSONDecodeError as e:
                print("Failed to parse memory indices from LLM response:", e)
                return []
            # 初始化选择的文件列表
            selected = []
            # 遍历得到索引值
            for idx in indices:
                # 检查索引有效性
                if isinstance(idx, int) and 0 <= idx < len(files):
                    # 将对应的文件名加入结果列表
                    selected.append(files[idx]["filename"])
                    # 超出最大数量则提前结束
                    if len(selected) >= max_items:
                        break
            # 返回相关记忆文件列表
            return selected
    except Exception:
        return []
    # 兜底的方案 近的消息中长度大于3的单词降级检索
    keywords = [word.lower for word in recent.split() if len(word) > 3]
    selected = []
    for f in files:
        text = (f["name"] + " " + f["description"]).lower()
        if any(kw in text for kw in keywords):
            selected.append(f["filename"])
            if len(selected) > max_items:
                break
    return selected


# 读取指定记忆文件内容 不存在则返回None
def read_memory_file(filename: str) -> str | None:
    # 拼接成完整的文件路
    path = MEMORY_DIR / filename
    # 检查文件是否存在
    if not path.exists():
        return None
    # 读取文件内容并返回
    return path.read_text(encoding=TEXT_ENCODING, errors="replace")


# 加载与对话相关的记忆内容 拼接为字符串返回
def load_memories(messages: list) -> str:
    # 选出相关的记忆文件名
    selected_files = select_relevant_memories(messages)
    # 如果没有相关记忆则直接返回空字符串
    if not selected_files:
        return ""
    # 初始化保存整合内容的列表 以分割标签开头
    parts = ["<relevant_memories>"]
    # 遍历所有相关记忆文件名
    for filename in selected_files:
        # 读取对应的文件内容
        content = read_memory_file(filename)
        # 如果内容不为空 则添加到parts中
        if content:
            parts.append(content)
    # 添加结尾的分割标签
    parts.append("</relevant_memories>")
    # 将所有部分用空行拼接为字符串返回
    return "\n\n".join(parts)


# 定义函数 列出所有记忆文件 并返回一个包含元数据的字典列表
def list_memory_files():
    # 初始化结果列表
    result = []
    # 遍历记忆目录下所有的markdown文件,并按名称排序
    for f in sorted(MEMORY_DIR.glob("*.md")):
        # 跳过主记忆文件 "MEMORY.md"
        if f.name == "MEMORY.md":
            continue
        # 读取文件内容 指定编码以及错误处理方式
        raw = f.read_text(encoding=TEXT_ENCODING, errors="replace")
        # 解析文件的frontmatter和正文内容
        meta, body = parse_frontmatter(raw)
        # 构造包含文件信息的字典并添加到结果列表
        result.append(
            {
                "filename": f.name,
                "name": meta.get("name", f.stem),
                "description": meta.get("description", ""),
                "type": meta.get("type", "user"),
                "body": body,
            }
        )
    return result


# 重建记忆索引文件的辅助函数
def _rebuild_index():
    # 初始化索引行的列表
    lines = []
    # 遍历记忆目录下所有markdown文件并排序
    for f in sorted(MEMORY_DIR.glob("*.md")):
        # 跳过主记忆文件
        if f.name == "MEMORY.md":
            continue
        # 读取文件内容
        raw = f.read_text(encoding=TEXT_ENCODING, errors="replace")
        # 解析frontmatter和正文
        meta, body = parse_frontmatter(raw)
        # 获取名称 默认用文件名去掉后缀
        name = meta.get("name", f.stem)
        # 获取描述 若无则取正文第一行前80字符
        desc = meta.get("description", body.split("\n")[0][:80])
        # 构建索引条目 添加到行列表
        lines.append(f"- [{name}]({f.name})-{desc}")
    # 将所有索引行拼接文本并写入索引文件
    MEMORY_INDEX.write_text(
        "\n".join(lines) + "\n" if lines else "", encoding=TEXT_ENCODING
    )


# 写入新的记忆文件 并重建索引
def write_memory_file(name: str, mem_type: str, description: str, body: str):
    # 生成文件slug(小写 空格和斜杠替换为连字符)
    slug = name.lower().replace(" ", "-").replace("/", "-")
    # 构建完整路径
    filepath = MEMORY_DIR / f"{slug}.md"
    # 按frontmatter格式写入文件内容
    filepath.write_text(
        f"---\nname: {name}\ndescription: {description}\ntype:{mem_type}\n---\n\n{body}\n",
        encoding=TEXT_ENCODING,
    )
    # 更新记忆索引
    _rebuild_index()
    # 返回文件路径对象
    return filepath


# 从最近的对话内容中提取新的记忆
def extract_memories(messages: list):
    # 初始化保存对话片段的列表
    dialogue_parts = []
    # 只处理最近的10条消息
    for msg in messages[-10:]:
        # 获取消息角色 默认问号
        role = msg.get("role", "?")
        # 获取消息文本
        text = message_text(msg).strip()
        # 若文本有内容 则格式化后加入对话片段
        if text:
            dialogue_parts.append(f"{role}: {text}")

    # 合并所有对话片段为多行字符串
    dialogue = "\n".join(dialogue_parts)
    # 如果合成结果为空 则不处理
    if not dialogue.strip:
        return
    # 获取所有已存在的记忆文件信息
    existing = list_memory_files()
    # 构建已存在记忆的描述文本 如无则为'(无)'
    existing_desc = (
        "\n".join(f"- {m['name']}: {m['description']}" for m in existing)
        if existing
        else " (无)"
    )
    # 构造prompt 提示LLM输出新记忆项(数组)
    prompt = (
        "从对话中提取用户偏好、约束或项目事实\n"
        "返回 JSON 数组, 每项 {name, type , description , body}。\n"
        "- name: 短 kebab-case 标识 \n"
        "- type: user | feedback | project | reference \n"
        "- description: 一行摘要供索引检索 \n"
        "- body: markdown 详情 \n"
        "若无新内容或已被现有记忆覆盖，返回 [] \n\n"
        f"现有记忆: \n{existing_desc}\n\n 对话:\n{dialogue[:4000]}"
    )
    try:
        # 发送消息到LLM 请求提取新记忆
        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
        )
        # 解析文本返回的文件内容
        text = llm_text(response)
        # 用正则匹配整个JSON数组
        match = re.search(r"\[.*\]", text, re.DOTALL)
        # 如果没有匹配到的数组则返回
        if not match:
            return
        # 解析为python对象
        items = json.loads(match.group())
        # 如果没有新内容则返回
        if not items:
            return
        # 记录成功写入的记忆条数
        count = 0
        # 遍历新记忆
        for mem in items:
            # 获取名称 默认用当前时间戳
            name = mem.get("name", f"memory_{int(time.time())}")
            # 获取类型 默认为"user"
            mem_type = mem.get("type", "user")
            # 获取摘要
            desc = mem.get("description", "")
            # 获取正文
            body = mem.get("body", "")
            # 描述和正文都非空写入新文件
            if desc and body:
                write_memory_file(name, mem_type, desc, body)
                count += 1
        # 若有新记忆则在控制台打印提醒
        if count:
            print(f"\n\x1b[33m[记忆: 提取了 {count} 条新记忆]\x1b[0m")
    # 捕获 JSON 解析失败并打印错误
    except json.JSONDecodeError as e:
        print("Failed to parse extracted memory JSON:", e)


# 合并记忆库 将冗余和冲突的信息归并 并限制数量
def consolidate_memories():
    # 获取全部记忆文件列表
    files = list_memory_files()
    # 若文件数量未达到合并阈值则直接返回
    if len(files) <= CONSOLIDATE_THRESHOLD:
        return
    # 构造所有记忆内容的目录文本 用于合并提示
    catalog = "\n\n".join(
        f"## {f['filename']}\nname: {f['name']}\ndescription: {f['description']}\n{f['body']}"
        for f in files
    )
    # 构造合并记忆的LLM提示语
    prompt = (
        "合并以下记忆文件。规则:\n"
        "1. 重复项合并为一条 \n 2.删除过时/矛盾的记忆\n"
        "3. 总数控制在 30条以内  \n 4.优先保留重要用户偏好\n"
        "返回JSON数组 每项: {name , type ,description , body}。\n\n"
        f"{catalog[:16000]}"
    )

    try:
        # 向LLM发起合并记忆请求
        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=3000,
        )
        # 解析返回的文本
        text = llm_text(response)
        # 用正则获取JSON数组
        match = re.search(r"\[.*\]", text, re.DOTALL)
        # 匹配不到直接返回
        if not match:
            return
        # 解析为Python对象
        items = json.loads(match.group())
        # 清除除"MEMORY.md"以外的所有记忆文件
        for f in MEMORY_DIR.glob("*.md"):
            if f.name != "MEMORY.md":
                f.unlink()
        # 遍历合并后的新记忆项并写入
        for mem in items:
            name = mem.get("name", f"memory_{int(time.time())}")
            mem_type = mem.get("type", "user")
            desc = mem.get("description", "")
            body = mem.get("body", "")
            if desc and body:
                write_memory_file(name, mem_type, desc, body)
        # 打印合并后的总结信息
        print(f"\n\x1b[33m[记忆: 已整理 {len(files)} → {len(items)} 条]\x1b[0m")
    except (json.JSONDecodeError, OSError) as e:
        print("Failed to consolidate memories:", e)
