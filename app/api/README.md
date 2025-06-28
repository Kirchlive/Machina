# LLM2LLM-Bridge API Server

## 🚀 Quick Start

1. **Install dependencies** (from project root):
   ```bash
   pip install -r requirements.txt
   ```

2. **Start the server**:
   ```bash
   uvicorn api_server.main:app --reload
   ```

3. **Access the API**:
   - API Base URL: http://127.0.0.1:8000
   - Interactive Docs: http://127.0.0.1:8000/docs
   - Alternative Docs: http://127.0.0.1:8000/redoc

## 📚 API Endpoints

### Health Check
```bash
GET /
```

### Get Available Models
```bash
GET /v1/models
```

### Start New Conversation
```bash
POST /v1/conversation
```
Returns:
```json
{
  "message": "New conversation created successfully.",
  "conversation_id": "conv_api_12345678"
}
```

### Send Message
```bash
POST /v1/conversation/{conversation_id}/message
```
Request Body:
```json
{
  "target_llm": "gpt4o_mini",
  "prompt": "Hello, how are you?"
}
```

## 📝 Example Usage

### Using cURL:
```bash
# 1. Create a new conversation
CONV_ID=$(curl -X POST http://localhost:8000/v1/conversation | jq -r '.conversation_id')

# 2. Send a message
curl -X POST http://localhost:8000/v1/conversation/$CONV_ID/message \
  -H "Content-Type: application/json" \
  -d '{
    "target_llm": "claude35_sonnet",
    "prompt": "What is the capital of France?"
  }'
```

### Using Python:
```python
import requests

# Create conversation
resp = requests.post("http://localhost:8000/v1/conversation")
conv_id = resp.json()["conversation_id"]

# Send message
resp = requests.post(
    f"http://localhost:8000/v1/conversation/{conv_id}/message",
    json={
        "target_llm": "gpt4o_mini",
        "prompt": "Tell me a joke"
    }
)
print(resp.json()["response"])
```

## 🛠️ Development

- The server automatically reloads when you save changes (thanks to `--reload` flag)
- Check logs in the terminal where you started the server
- API events are logged to `bridge_events.jsonl`