import json
import os

# 目标历史记录文件
path = r'C:\Users\12263\.cursor\projects\c-Dev-capstoneProject\agent-transcripts\34203240-f8ce-4422-abfb-20fdfb406ea1\34203240-f8ce-4422-abfb-20fdfb406ea1.jsonl'
output_path = r'c:\Dev\capstoneProject\ui_stable_recovered.py'

print(f"开始从 {path} 搜索稳定版代码...")

found_count = 0
# 我们寻找包含 TRANSLATIONS 字典，且长度在 15000 到 35000 字符之间的 Write 调用
# 这个长度范围通常对应 500-800 行代码
with open(path, 'r', encoding='utf-8') as f:
    for i, line in enumerate(f, 1):
        if '"name": "Write"' in line and 'ui.py' in line:
            try:
                data = json.loads(line)
                # 遍历消息内容寻找工具调用
                contents = ""
                for item in data.get('message', {}).get('content', []):
                    if item.get('type') == 'tool_use' and item.get('name') == 'Write':
                        args = item.get('arguments', {})
                        if 'ui.py' in args.get('path', ''):
                            contents = args.get('contents', '')
                            
                if contents and "TRANSLATIONS" in contents and len(contents) > 10000:
                    found_count += 1
                    # 我们倾向于找较早期的版本（但已经有了 i18n）
                    # 根据之前的分析，行号 134 附近是关键转折点
                    if i > 100:
                        with open(output_path, 'w', encoding='utf-8') as out:
                            out.write(contents)
                        print(f"成功提取！来源行号: {i}, 代码长度: {len(contents)}")
                        print(f"已保存至: {output_path}")
                        # 找到第一个符合条件的就退出（这通常是实现 i18n 后的第一个完整版）
                        exit(0)
            except Exception as e:
                continue

if found_count == 0:
    print("未找到符合条件的 Write 调用。")
