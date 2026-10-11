from dotenv import load_dotenv; load_dotenv()
import os, json
from google import genai
from google.genai import types as T
client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])
r = client.models.generate_content(
    model='gemini-3.1-flash-lite',
    contents='Respond with JSON only: {"ok": true}',
    config=T.GenerateContentConfig(temperature=0, response_mime_type='application/json')
)
print(r.text)
