from pathlib import Path
from dotenv import load_dotenv, find_dotenv
import os
from openai import OpenAI

# Load .env from the current working directory (the folder you run the command in)
env_path = find_dotenv(filename=".env", usecwd=True)
load_dotenv(env_path, override=False)

print("Loaded .env:", env_path or "<none>")
print("CWD:", os.getcwd())
print("API key starts with:", os.getenv("OPENAI_API_KEY", "")[:8])

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])  # will raise KeyError if missing

resp = client.responses.create(
    model="gpt-4.1-mini",
    input=[{"role":"user","content":[{"type":"input_text","text":"Say 'OK' and nothing else."}]}]
)
print("Response:", resp.output[0].content[0].text)
