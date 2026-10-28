"""Publishing-preparation regressions; no host CLI, network or third-party packages."""

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/story-publish/scripts/check-publish-format.py"
spec = importlib.util.spec_from_file_location("publish_format", SCRIPT)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


LONG = """> 目标平台：番茄小说；核验日期：2026-10-25

# 书本名称：春风：第2年

- 作者/笔名：待确认

## 封面

- 模式：仅提示词
- 状态：建议，图片未生成
- 提示词：
````text
## 画面构图
```text
山间春风
```
````
- 图片：未生成

## 阅读标签

- 主分类：
- 主题：
- 角色：
- 情节：

## 内容标签

- 情节：
- 情感：
- 人设：
- 世界观：

## 作品简介

待作者确认

## 待作者按照发布界面核实的内容

尚有留空项；资料不代表平台可提交。

## 待平台核实

账号等级未知。

## 来源说明

作者确认与参考资料。
"""

SHORT = LONG.replace(
    "> 目标平台：番茄小说；核验日期：2026-10-25",
    "> 目标平台：番茄小说；核验日期：2026-10-28\n> 作品类型：短故事",
).replace(
    "- 作者/笔名：待确认",
    "- 作者/笔名：待确认\n- 是否使用AI：\n- 试读比例：\n- 发布协议：待作者阅读确认",
)
SHORT = SHORT[:SHORT.index("## 阅读标签")] + """## 作品分类

- 主分类：婚姻家庭
- 情节：先婚后爱、重生
- 角色：白月光
- 情绪：甜宠
- 背景：现代

""" + SHORT[SHORT.index("## 作品简介"):]


class PublishFormatTests(unittest.TestCase):
    def test_long_and_legacy_metadata(self):
        self.assertEqual(checker.validate(LONG), [])
        self.assertEqual(checker.validate(LONG.replace("> 目标平台", "> 作品类型：长篇\n> 目标平台")), [])

    def test_short(self):
        self.assertEqual(checker.validate(SHORT), [])

    def test_source_must_be_last(self):
        self.assertTrue(checker.validate(LONG.replace("## 封面", "## 来源说明", 1)))

    def test_name_first(self):
        self.assertTrue(checker.validate(LONG.replace("# 书本名称：春风：第2年", "# 番茄建书资料")))

    def test_merged_tag_lines_rejected(self):
        self.assertTrue(checker.validate(LONG.replace("- 主分类：\n- 主题：", "- 主分类：年代；主题：日常")))

    def test_fenced_prompt_headings(self):
        self.assertEqual(checker.validate(LONG.replace("````text", "~~~~text").replace("````", "~~~~")), [])

    def test_missing_cover_field(self):
        self.assertTrue(checker.validate(LONG.replace("- 图片：未生成", "")))

    def test_title_boundaries(self):
        self.assertEqual(checker.validate_title("春" * 12 + "：12"), [])
        self.assertTrue(checker.validate_title("春" * 13 + "：12"))
        self.assertEqual(checker.validate_title("春风……又一年"), [])
        for title in ("春风:归来", "春风!", "春风🙂", ""):
            with self.subTest(title=title):
                self.assertTrue(checker.validate_title(title))

    def test_short_field_membership(self):
        self.assertTrue(checker.validate(SHORT.replace("角色：白月光", "角色：现代")))
        self.assertTrue(checker.validate(SHORT.replace("背景：现代", "背景：未知分类")))

    def test_total_limit_across_groups(self):
        eight = SHORT.replace("情节：先婚后爱、重生", "情节：先婚后爱、重生、穿越、暗恋")
        self.assertEqual(checker.validate(eight), [])
        self.assertTrue(checker.validate(eight.replace("背景：现代", "背景：现代、古代")))

    def test_duplicate(self):
        self.assertTrue(checker.validate(SHORT.replace("情绪：甜宠", "情绪：甜宠、甜宠")))

    def test_blank_preparation_fields_allowed(self):
        self.assertEqual(checker.validate(SHORT.replace("主分类：婚姻家庭", "主分类：")), [])

    def test_short_must_identify_type(self):
        self.assertTrue(checker.validate(SHORT.replace("> 作品类型：短故事", "")))
        self.assertTrue(checker.validate(SHORT.replace("短故事", "其他")))

    def test_short_settings_and_long_leak(self):
        self.assertTrue(checker.validate(SHORT.replace("- 是否使用AI：", "")))
        self.assertTrue(checker.validate(SHORT.replace("- 试读比例：", "- 签约模式：连载")))

    def test_reference_counts_and_evidence(self):
        options = checker.short_candidates()
        self.assertEqual({key: len(value) for key, value in options.items()},
                         {"主分类": 24, "情节": 34, "角色": 26, "情绪": 8, "背景": 10})
        reference = ROOT / "skills/story-publish/references/fanqie-short-2026-10-28.md"
        import re
        for link in re.findall(r"\]\((evidence/[^)]+)\)", reference.read_text(encoding="utf-8")):
            self.assertTrue((reference.parent / link).is_file(), link)

    def test_cli_unicode_paths_readonly_and_failure(self):
        with tempfile.TemporaryDirectory(prefix="publish check ") as directory:
            path = Path(directory) / "发布资料-番茄小说.md"
            path.write_text("\ufeff" + SHORT, encoding="utf-8")
            before = path.read_bytes()
            env = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
            result = subprocess.run([sys.executable, str(SCRIPT), str(path)],
                                    capture_output=True, env=env)
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8"))
            self.assertEqual(path.read_bytes(), before)
            path.write_text("# 错误格式", encoding="utf-8")
            self.assertEqual(subprocess.run([sys.executable, str(SCRIPT), str(path)],
                             capture_output=True, env=env).returncode, 1)
            path.unlink()
            self.assertEqual(subprocess.run([sys.executable, str(SCRIPT), str(path)],
                             capture_output=True, env=env).returncode, 1)


if __name__ == "__main__":
    unittest.main()
