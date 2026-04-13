import sys
sys.path.insert(0, '.')

from src.util.invoke_ai import invoke_ai

# Test the invoke_ai function
system_message = "You are a helpful assistant."
user_message = "What is 2 + 2?"

try:
    response = invoke_ai(system_message, user_message)
    print("Response from Ollama:")
    print(response)
except Exception as e:
    print(f"Error: {e}")
    print("Make sure Ollama is running and the qwen3:4b model is pulled.")
