
import requests


class LocalLLM:

    def __init__(self, model="qwen2.5:1.5b"):
        self.model = model
        self.url = "http://localhost:11434/api/chat"

    def generate_response(self, prompt):

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "stream": False
        }

        try:
            response = requests.post(
                self.url,
                json=payload,
                timeout=120
            )

            response.raise_for_status()

            result = response.json()

            return result["message"]["content"]

        except requests.exceptions.RequestException as error:
            return f"Error connecting to Ollama: {error}"


if __name__ == "__main__":

    llm = LocalLLM()

    prompt = "Explain what an MCP server is in simple words."

    answer = llm.generate_response(prompt)

    print("\nQwen Response:")
    print(answer)
