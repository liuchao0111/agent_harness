# 从config模块导入SKILLS_DIR(技能目录) 和 TEXT_ENCODING(文本编码格式)
from config import SKILLS_DIR, TEXT_ENCODING

# 从utils模块导入parse_frontmatter方法
from utils import parse_frontmatter

# 定义一个全局字典，用于存放技能信息 键为字符串 值为字典
SKILL_REGISTRY: dict[str, dict] = {}


# 定义一个私有函数 用于扫描目录下的所有技能
def _scan_skills():
    # 如果目录不存在 则直接返回
    if not SKILLS_DIR.exists():
        return
    # 遍历技能下所有的子目录 按名称排序
    for d in sorted(SKILLS_DIR.iterdir()):
        # 如果不是目录 则跳过
        if not d.is_dir():
            continue
        # 构造manifest文件不存在 则跳过
        mainfest = d / "SKILL.md"
        # 如果mainfest 文件不存在 则跳过
        if not mainfest.exists():
            continue
        # 读取mainfest文件内容 指定编码方式和错误处理方式
        raw = mainfest.read_text(encoding=TEXT_ENCODING, errors="replace")
        # 解析frontmatrer 获取元信息和正文内容
        meta, _body = parse_frontmatter(raw)
        # 获取技能名称 , 优先元信息中的name字段 否则用目录名
        name = meta.get("name", d.name)
        # 获取技能描述 优先元信息中的description的字段 否则用一行内容
        description = meta.get("description", raw.split("\n")[0].lstrip("#").strip())
        # 将技能信息存入到全局注册表
        SKILL_REGISTRY[name] = {
            "name": name,
            "description": description,
            "content": raw,
        }


# 定义一个加载函数
def load_skill(name: str) -> str:
    # 从注册表中获取技能信息
    skill = SKILL_REGISTRY.get(name)
    # 如果没有找到 返回提示信息
    if not skill:
        return f"未找到技能: {name}"
    # 在控制台打印加载提示（带颜色）
    print(f"\x1b[90m[技能] 已加载 {name}\x1b[0m")
    # 返回技能内容
    return skill["content"]


# 调用扫描函数 初始化技能注册表
_scan_skills()
