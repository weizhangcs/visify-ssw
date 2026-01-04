import logging
import sys
from pathlib import Path

# 1. 环境初始化 (无需 Django setup，因为 TextAnalyzer 是纯逻辑算子)
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.append(str(BASE_DIR))

from apps.atomflow.refinery.services.text_analyzer import TextAnalyzerService  # noqa: E402

# 配置日志输出到控制台
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def run_test():
    print("=" * 60)
    print("🚀 TextAnalyzerService 本地逻辑验证 (Mock Data)")
    print("=" * 60)

    # --- Mock Data 1: 脏数据清洗测试 ---
    # 包含: BOM头, HTML标签, <br>, ASS标签, 环境音 [], ()
    srt_dirty = """\ufeff1
00:00:01,000 --> 00:00:03,000
<b>车小小</b>，<br>好戏开场了</br>

2
00:00:04,500 --> 00:00:06,000
[音乐起]不对，{\\an8}从现在起(掌声)

3
00:00:07,000 --> 00:00:09,000
<font color="#ff0000">我就是</font>和风集团继承人
"""

    print("\n[Case 1] 脏数据清洗测试")
    print("-" * 40)
    results_1 = TextAnalyzerService.run(srt_dirty)
    for item in results_1:
        print(f"[{item['index']}] {item['start_time']}s -> {item['end_time']}s")
        print(f"    原文清洗结果: [{item['content']}]")

    # 预期验证
    assert results_1[0]["content"] == "车小小，好戏开场了", "HTML标签或换行清洗失败"
    assert results_1[1]["content"] == "不对，从现在起", "环境音或ASS标签清洗失败"
    assert results_1[2]["content"] == "我就是和风集团继承人", "Font标签清洗失败"
    print("✅ Case 1 通过")

    # --- Mock Data 2: 智能换行合并测试 ---
    # 包含: 中文+中文 (无空格), 英文+英文 (有空格), 中文+英文 (有空格)
    srt_multiline = """1
00:00:01,000 --> 00:00:03,000
车小小，好戏开场了
我今天一定要好好地进行表现

2
00:00:04,000 --> 00:00:06,000
Hello
World

3
00:00:07,000 --> 00:00:09,000
Hello
世界

4
00:00:10,000 --> 00:00:12,000
你好
World
"""

    print("\n[Case 2] 智能换行合并测试")
    print("-" * 40)
    results_2 = TextAnalyzerService.run(srt_multiline)
    for item in results_2:
        print(f"[{item['index']}] 合并结果: [{item['content']}]")

    # 预期验证
    assert results_2[0]["content"] == "车小小，好戏开场了我今天一定要好好地进行表现", "中文合并错误 (应无空格)"
    assert results_2[1]["content"] == "Hello World", "英文合并错误 (应有空格)"
    assert results_2[2]["content"] == "Hello 世界", "英中合并错误 (应有空格)"
    assert results_2[3]["content"] == "你好 World", "中英合并错误 (应有空格)"
    print("✅ Case 2 通过")


if __name__ == "__main__":
    run_test()
