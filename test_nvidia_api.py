import os
from openai import OpenAI

client = OpenAI(
  base_url = "https://integrate.api.nvidia.com/v1",
  api_key = os.environ.get("NVIDIA_API_KEY")
)

try:
    completion = client.chat.completions.create(
      model="minimaxai/minimax-m2.1",
      messages=[{"role":"user","content":"你好"}],
      temperature=0.2,
      max_tokens=2048,
      stream=True
    )

    for chunk in completion:
      if not getattr(chunk, "choices", None):
        continue
      if chunk.choices[0].delta.content is not None:
        print(chunk.choices[0].delta.content, end="")
    print("\n[SUCCESS]")
except Exception as e:
    print(f"\n[ERROR] {e}")
