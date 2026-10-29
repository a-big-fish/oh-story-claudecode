"""Read-only check of a 番茄 publishing-preparation document: layout, candidates, limits."""

import argparse
from pathlib import Path
import re
import sys


REFERENCES = Path(__file__).resolve().parents[1] / "references"
TAIL = ["作品简介", "待作者按照发布界面核实的内容", "待平台核实", "来源说明"]
LONG_SECTIONS = ["封面", "阅读标签", "内容标签", *TAIL]
SHORT_SECTIONS = ["封面", "作品分类", *TAIL]
READING_FILES = {"男频": "fanqie-reading-male.md", "女频": "fanqie-reading-female.md"}
SHORT_TOTAL = 8
LONG_TITLE_SYMBOLS = frozenset("！，？：【】")


def load_options(name):
    """Return {field: (candidates, limit)} from a reference's '## 字段 / 规则 / 候选值' blocks."""
    options = {}
    for block in re.split(r"^## ", (REFERENCES / name).read_text(encoding="utf-8"), flags=re.M)[1:]:
        field, _, body = block.partition("\n")
        values = re.search(r"^候选值：(.+?)。?\s*$", body, re.M)
        if values:
            limit = re.search(r"^规则：.*?选(\d+)个", body, re.M)
            options[field.strip()] = (set(values[1].split("、")), int(limit[1]) if limit else None)
    if not options:
        raise ValueError(f"{name} 没有可读的候选值。")
    return options


def headings_outside_fences(lines):
    headings, fence = [], None
    for index, line in enumerate(lines):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
        elif marker:
            fence = marker[1]
        elif match := re.match(r"^(#{1,6})\s+(.+?)\s*$", line):
            headings.append((index, len(match[1]), match[2]))
    return headings


def section_lines(lines, headings, title):
    for position, (start, _, name) in enumerate(headings):
        if name == title:
            end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
            return [line for line in lines[start + 1:end] if line.strip()]
    return None


def field_values(lines, section, errors):
    """Parse '- 字段：值、值' lines; every sub-field must sit on its own line."""
    fields = {}
    for line in lines:
        match = re.fullmatch(r"- ([^：:]+)：(.*)", line)
        if not match:
            errors.append(f"{section}的每个子字段必须写成独立的「- 字段：值」行。")
            continue
        if re.search(r"[^\s、，,]+\s*[：:]", match[2]):
            errors.append(f"{section}的 {match[1]} 行混入了其他子字段，要拆行。")
        fields[match[1]] = [value.strip() for value in match[2].split("、") if value.strip()]
    return fields


def check_tags(section, fields, expected, options, errors):
    if list(fields) != expected:
        errors.append(f"{section}子字段必须依次列出：" + "、".join(expected) + "。")
    for field, values in fields.items():
        if field not in options:
            continue
        candidates, limit = options[field]
        if len(values) != len(set(values)):
            errors.append(f"{section}的 {field} 有重复值。")
        if limit and len(values) > limit:
            errors.append(f"{section}的 {field} 选了 {len(values)} 个，最多 {limit} 个。")
        for value in values:
            if value not in candidates:
                errors.append(f"{section}的 {field} 不在候选里：{value}。")


def title_warnings(text):
    """Platform title rules, reported as warnings: an author-chosen title is the author's call."""
    match = re.search(r"^# 书本名称：\s*(.*?)\s*$", text, re.M)
    title = match[1] if match else ""
    if not title or title == "待作者确认":
        return []
    warnings = []
    if any(char.isspace() for char in title):
        warnings.append("书名不能有空格。")
    if re.search(r"^> 作品类型：\s*短故事\s*$", text, re.M):
        length = sum(0.5 if ord(char) < 128 else 1 for char in title)
        if length > 25:
            warnings.append(f"短故事书名计 {length:g} 个字符，番茄上限 25（半角算半个）。")
        return warnings
    if len(title) > 15:
        warnings.append(f"书名 {len(title)} 个字符，番茄长篇上限 15。")
    invalid = "".join(dict.fromkeys(c for c in title if not c.isalnum() and not c.isspace() and c not in LONG_TITLE_SYMBOLS))
    if invalid:
        warnings.append(f"番茄长篇书名只能用全角！，？：【】，不能用：{invalid}")
    return warnings


def validate(text):
    lines = text.lstrip("﻿").splitlines()
    headings = headings_outside_fences(lines)
    errors = []

    if not headings or headings[0][1] != 1 or not re.fullmatch(r"书本名称：\s*\S.*", headings[0][2]):
        return ["第一个标题必须是「# 书本名称：<书名>」，前面不放总标题。"]
    title_line = headings[0][0]
    if any(line.strip() and not line.startswith("> ") for line in lines[:title_line]) or not any(
        line.strip() for line in lines[:title_line]
    ):
        errors.append("书名前只能有引用块元信息。")

    types = re.findall(r"^> 作品类型：\s*(.*?)\s*$", "\n".join(lines[:title_line]), re.M)
    if types not in ([], ["长篇"], ["短故事"]):
        errors.append("作品类型元信息只能写一次，且为长篇或短故事。")
    is_short = types == ["短故事"]

    sections = SHORT_SECTIONS if is_short else LONG_SECTIONS
    if [(level, name) for _, level, name in headings[1:]] != [(2, name) for name in sections]:
        errors.append("小节必须依次为：" + " → ".join(sections) + "，都用二级标题。")

    basics = "\n".join(lines[title_line + 1:headings[1][0] if len(headings) > 1 else len(lines)])
    if is_short:
        for field in ("是否使用AI", "试读比例", "发布协议"):
            if not re.search(rf"^- {field}：", basics, re.M):
                errors.append(f"短故事基础资料缺少 {field}。")
        if re.search(r"^- (?:签约模式|目标读者|主角[12])：", basics, re.M):
            errors.append("短故事不写长篇的签约模式、目标读者或主角字段。")

    cover = section_lines(lines, headings, "封面")
    if cover is not None:
        for field in ("模式", "状态", "提示词", "图片"):
            if not any(line.startswith(f"- {field}：") for line in cover):
                errors.append(f"封面小节缺少 {field}。")

    if is_short:
        options = load_options("fanqie-short.md")
        block = section_lines(lines, headings, "作品分类")
        if block is not None:
            fields = field_values(block, "作品分类", errors)
            check_tags("作品分类", fields, list(options), options, errors)
            total = sum(len(values) for values in fields.values())
            if total > SHORT_TOTAL:
                errors.append(f"作品分类合计 {total} 个，五组合计最多 {SHORT_TOTAL} 个。")
        return errors

    audience = re.search(r"^- 目标读者：\s*(\S*)", basics, re.M)
    audience = audience[1] if audience else ""
    reading = section_lines(lines, headings, "阅读标签")
    if reading is not None:
        fields = field_values(reading, "阅读标签", errors)
        expected = ["主分类", "主题", "角色", "情节"]
        if audience in READING_FILES:
            check_tags("阅读标签", fields, expected, load_options(READING_FILES[audience]), errors)
        else:
            check_tags("阅读标签", fields, expected, {}, errors)
            if any(fields.values()):
                errors.append("填阅读标签前先确定目标读者（男频或女频）。")
    content = section_lines(lines, headings, "内容标签")
    if content is not None:
        fields = field_values(content, "内容标签", errors)
        check_tags("内容标签", fields, ["情节", "情感", "人设", "世界观"],
                   load_options("fanqie-content-tags.md"), errors)
    # Blank fields are allowed: this is a preparation document, not submission readiness.
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    try:
        text = args.file.read_text(encoding="utf-8-sig")
        errors, warnings = validate(text), title_warnings(text)
    except (OSError, UnicodeError, ValueError) as error:
        errors, warnings = [str(error)], []
    for warning in warnings:
        print(f"WARN: {warning}")
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    if not errors:
        print("PASS: 发布资料结构、分类与标签")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
