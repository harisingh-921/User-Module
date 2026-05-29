import os
import toml
from openai import OpenAI
from pydantic import BaseModel, Field
from typing import List

class User(BaseModel):
    userName: str
    firstName: str

class UserMasterResult(BaseModel):
    document_name: str
    users: List[User]

secrets_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".streamlit", "secrets.toml")
secrets = toml.load(secrets_path)
key = secrets.get("GEMINI_API_KEY")

client = OpenAI(
    api_key=key,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

try:
    print("Testing gemini-2.5-flash with parse()...")
    completion = client.chat.completions.parse(
        model="gemini-2.5-flash",
        messages=[
            {"role": "system", "content": "You extract user list."},
            {"role": "user", "content": "firstName=John, userName=john123"}
        ],
        response_format=UserMasterResult,
        timeout=30
    )
    print("Success!")
    print(completion.choices[0].message.parsed)
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
