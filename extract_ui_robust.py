import sys

path = r'C:\Users\12263\.cursor\projects\c-Dev-capstoneProject\agent-transcripts\34203240-f8ce-4422-abfb-20fdfb406ea1\34203240-f8ce-4422-abfb-20fdfb406ea1.jsonl'

with open(path, 'r', encoding='utf-8') as f:
    for i, line in enumerate(f, 1):
        if len(line) > 10000 and 'ui.py' in line:
            # Found a candidate line. Now try to extract the contents field.
            # The format is likely ... "contents": "CODE", "path": "ui.py" ...
            # or ... "path": "ui.py", "contents": "CODE" ...
            start_marker = '"contents": "'
            end_marker = '", "path":'
            if start_marker in line:
                start_idx = line.find(start_marker) + len(start_marker)
                end_idx = line.find(end_marker, start_idx)
                if end_idx != -1:
                    code_escaped = line[start_idx:end_idx]
                    # Unescape the code
                    # The JSON unescaping is basically replacing \n with actual newline, etc.
                    # We can use json.loads to do it correctly by wrapping it in quotes.
                    import json
                    try:
                        code = json.loads('"' + code_escaped + '"')
                        if "TRANSLATIONS =" in code:
                            with open(f'ui_restored_{i}.py', 'w', encoding='utf-8') as out:
                                out.write(code)
                            print(f"Extracted ui.py from line {i}, size {len(code)}")
                    except:
                        continue
