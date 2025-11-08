import requests
import json
url = "http://localhost:3002/v1/chat/completions"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer 2412"
}
data = {
    "model": "openai/gpt-4.1",
    "messages": [
        {"role": "system", "content": "Eres un asistente útil."},
        {"role": "user", "content": "Hola, ¿cómo estás?"}
    ],
    "max_tokens": 200
} 
response = requests.post(url, headers=headers, data=json.dumps(data))
print(response.json())