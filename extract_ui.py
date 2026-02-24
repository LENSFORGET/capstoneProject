import json
import sys

path = r'C:\Users\12263\.cursor\projects\c-Dev-capstoneProject\agent-transcripts\dc2f5806-f6db-448a-a061-ada892f9a83c\dc2f5806-f6db-448a-a061-ada892f9a83c.jsonl'

with open(path, 'r', encoding='utf-8') as f:
    for i, line in enumerate(f, 1):
        if '"name": "Write"' in line and 'ui.py' in line:
            try:
                data = json.loads(line)
                for item in data.get('message', {}).get('content', []):
                    if item.get('type') == 'tool_use' and item.get('name') == 'Write':
                        args = item.get('arguments', {})
                        if 'ui.py' in args.get('path', ''):
                            contents = args.get('contents', '')
                            if len(contents) > 10000:
                                with open('ui_restored.py', 'w', encoding='utf-8') as out:
                                    out.write(contents)
                                print(f"Successfully extracted ui.py from line {i}, size: {len(contents)}")
                                sys.exit(0)
            except:
                continue
