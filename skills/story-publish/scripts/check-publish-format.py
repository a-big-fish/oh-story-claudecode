"""Read-only validation of a publishing-preparation Markdown document."""

import argparse
from pathlib import Path
import re
import sys
import unicodedata


TITLE_MAX_CHARS = 15
CHINESE_SYMBOLS = frozenset("，。！？；：、（）【】《》〈〉「」『』“”‘’〔〕［］｛｝—…·～％＃＆＠＊＋－／＝＜＞｜＿￥")


SECTIONS = [
    "封面",
    "阅读标签",
    "内容标签",
    "作品简介",
    "待作者按照发布界面核实的内容",
    "待平台核实",
    "来源说明",
]
TAG_FIELDS = {
    "阅读标签": ["主分类", "主题", "角色", "情节"],
    "内容标签": ["情节", "情感", "人设", "世界观"],
}
SHORT_FIELDS = ["主分类", "情节", "角色", "情绪", "背景"]
SHORT_SECTIONS = ["封面", "作品分类", *SECTIONS[3:]]


def short_candidates():
    """Read the maintained field-scoped Markdown list, not a second inventory."""
    reference = Path(__file__).resolve().parents[1] / "references/fanqie-short-2026-10-28.md"
    result = {}
    for line in reference.read_text(encoding="utf-8").splitlines():
        columns = [column.strip() for column in line.strip("|").split("|")]
        if len(columns) == 2 and columns[0] in SHORT_FIELDS:
            result[columns[0]] = set(columns[1].split("、"))
    if set(result) != set(SHORT_FIELDS):
        raise ValueError("短故事分类参考缺少候选字段。")
    return result


def validate_title(title):
    title = title.strip()
    errors = []
    if not title:
        errors.append("书本名称不能为空。")
    if len(title) > TITLE_MAX_CHARS:
        errors.append(f"书本名称共 {len(title)} 个字符，最多允许 {TITLE_MAX_CHARS} 个；数字和符号也计数。")
    invalid = list(dict.fromkeys(
        char for char in title
        if unicodedata.category(char)[0] in {"P", "S"} and char not in CHINESE_SYMBOLS
    ))
    if invalid:
        errors.append("书本名称必须使用中文符号，不允许：" + "、".join(invalid) + "。")
    return errors


def validate(text):
    lines = text.lstrip("\ufeff").splitlines()
    errors = []
    headings = []
    fence = None
    for index, line in enumerate(lines):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
            continue
        if marker:
            fence = marker[1]
            continue
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            headings.append((index, len(match[1]), match[2]))

    if not headings or headings[0][1] != 1 or not re.fullmatch(
        r"书本名称：\s*\S.*", headings[0][2]
    ):
        errors.append("首个正文标题必须是 # 书本名称：<书名>，不能使用资料总标题。")
    else:
        errors.extend(validate_title(headings[0][2].partition("：")[2]))
        metadata = [line for line in lines[: headings[0][0]] if line.strip()]
        if not metadata or any(not line.startswith("> ") for line in metadata):
            errors.append("书名前只能有引用块元信息和空行。")

    metadata_end = headings[0][0] if headings else 0
    types = re.findall(r"^> 作品类型：\s*(.*?)\s*$", "\n".join(lines[:metadata_end]), re.M)
    is_short = types == ["短故事"]
    if types and types not in (["短故事"], ["长篇"]):
        errors.append("作品类型元信息须唯一且为长篇或短故事。")
    sections = SHORT_SECTIONS if is_short else SECTIONS
    tag_fields = {"作品分类": SHORT_FIELDS} if is_short else TAG_FIELDS
    if [(level, title) for _, level, title in headings[1:]] != [
        (2, section) for section in sections
    ]:
        errors.append("小节必须依次为：" + " → ".join(sections) + "，且使用二级标题。")
    if is_short and headings:
        end = headings[1][0] if len(headings) > 1 else len(lines)
        basics = "\n".join(lines[headings[0][0] + 1:end])
        for field in ("是否使用AI", "试读比例", "发布协议"):
            if not re.search(r"^- " + field + "：", basics, re.M):
                errors.append(f"短故事基础资料缺少 {field} 字段。")
        if re.search(r"^- (?:签约模式|目标读者|主角[12])：", basics, re.M):
            errors.append("短故事基础资料不能套用长篇签约模式、频道或主角字段。")

    covers = [(position, item) for position, item in enumerate(headings) if item[2] == "封面"]
    if len(covers) == 1:
        position, (start, _, _) = covers[0]
        end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        content = "\n".join(lines[start + 1 : end])
        for field in ("模式", "状态", "提示词", "图片"):
            if not re.search(r"^- " + field + "：", content, re.M):
                errors.append(f"封面小节缺少 {field} 字段。")

    candidates = short_candidates() if is_short else {}
    total = 0
    for section, expected in tag_fields.items():
        matches = [(position, item) for position, item in enumerate(headings) if item[2] == section]
        if len(matches) != 1:
            continue
        position, (start, _, _) = matches[0]
        end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        content = [line for line in lines[start + 1 : end] if line.strip()]
        fields = []
        for line in content:
            match = re.fullmatch(r"- ([^：:]+)：(.*)", line)
            if not match:
                errors.append(f"{section}的每个子字段必须使用独立的 '- 字段：值' 行。")
                continue
            fields.append(match[1])
            if re.search(r"(?:主分类|主题|角色|情节|情感|人设|世界观|情绪|背景)\s*[:：]", match[2]):
                errors.append(f"{section}的 {match[1]} 行混入其他子字段，必须拆行。")
            if is_short and match[1] in candidates:
                values = [value.strip() for value in match[2].split("、") if value.strip()]
                total += len(values)
                if len(values) != len(set(values)):
                    errors.append(f"作品分类的 {match[1]} 存在重复值。")
                for value in values:
                    if value not in candidates[match[1]]:
                        errors.append(f"作品分类的 {match[1]} 值不在本字段候选中：{value}。")
        if fields != expected:
            errors.append(f"{section}子字段必须依次独立列出：" + "、".join(expected) + "。")
    if total > 8:
        errors.append(f"短故事分类共 {total} 个，五组总计最多 8 个。")
    # This is a preparation document: blank fields are allowed, not submission readiness.
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    try:
        errors = validate(args.file.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print("PASS: publishing document order, title and tag layout")
    return 0


if __name__ == "__main__":
    sys.exit(main())
