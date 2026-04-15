import os
import re

api_path = r"c:\AI Smart PDF Editor\backend\api.py"
run_path = r"c:\AI Smart PDF Editor\run.py"

# Update api.py
with open(api_path, "r", encoding="utf-8") as f:
    api_content = f.read()

# 1. Add import asyncio if not there
if "import asyncio" not in api_content:
    api_content = "import asyncio\n" + api_content

# 2. Replace all async def with def
api_content = api_content.replace("async def ", "def ")

# 3. Handle translate_text await
api_content = api_content.replace(
    "await translate_text(text, target_language, source_language)",
    "asyncio.run(translate_text(text, target_language, source_language))"
)

with open(api_path, "w", encoding="utf-8") as f:
    f.write(api_content)
    
print("Updated api.py")

# Update run.py
with open(run_path, "r", encoding="utf-8") as f:
    run_content = f.read()

# Replace backend command to remove --reload and add --workers 4
run_content = re.sub(
    r"backend_command\s*=\s*f\"uvicorn backend\.main:app --reload --host \{backend_host\} --port \{backend_port\}\"",
    "backend_command = f\"uvicorn backend.main:app --workers 4 --host {backend_host} --port {backend_port}\"",
    run_content
)

with open(run_path, "w", encoding="utf-8") as f:
    f.write(run_content)

print("Updated run.py")
