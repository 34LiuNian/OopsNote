import json
import sys

try:
    with open("backend/storage/llm_payloads.log", "r", encoding="utf-8") as f:
        # Read the last line
        lines = f.readlines()
        if not lines:
            print("Log is empty")
            sys.exit(1)
        last_line = lines[-1]
        data = json.loads(last_line)
        response = data.get("response", "")
        with open("_tmp_response.txt", "w", encoding="utf-8") as out:
            out.write(response)
        print(f"Successfully extracted {len(response)} chars to _tmp_response.txt")
except Exception as e:
    print(f"Error: {e}")
