import os
import sys
import toml
from openai import OpenAI

secrets_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".streamlit", "secrets.toml")
if os.path.exists(secrets_path):
    secrets = toml.load(secrets_path)
else:
    secrets = {}

print("Loaded secrets:", list(secrets.keys()))

keys_to_test = [
    ("OPENAI_API_KEY", secrets.get("OPENAI_API_KEY")),
    ("OPENAI_API_KEY_2", secrets.get("OPENAI_API_KEY_2")),
    ("GEMINI_API_KEY", secrets.get("GEMINI_API_KEY")),
    ("GEMINI_API_KEY_2", secrets.get("GEMINI_API_KEY_2")),
    ("GEMINI_API_KEY_3", secrets.get("GEMINI_API_KEY_3")),
]

for name, key in keys_to_test:
    if not key:
        print(f"{name}: Not found")
        continue
    
    print(f"\n--- Testing {name} ---")
    try:
        if key.startswith("AIzaSy"):
            client = OpenAI(
                api_key=key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
            )
            model = "gemini-2.5-flash"
        else:
            client = OpenAI(api_key=key)
            model = "gpt-4o-mini"
            
        print(f"Creating completion with model {model}...")
        completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Hello, responding with exactly 1 word: 'Success'."}],
            timeout=10
        )
        print(f"Result: {completion.choices[0].message.content.strip()}")
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")
