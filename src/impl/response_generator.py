from typing import List
from src.interface.base_response_generator import BaseResponseGenerator
from src.util.invoke_ai import invoke_ai


SYSTEM_PROMPT = """
dont speak too much,
be concise and to the point. Always use the provided context to answer the question. 
If the answer is not in the context, say "I don't know". 
Do not provide any information that is not in the context and dont type any extra info just PROVIDE THE ANSWER.

"""


class ResponseGenerator(BaseResponseGenerator):
    def generate_response(self, query: str, context: List[str]) -> str:
        """Generate a response using Qwen 3 LLM via Ollama."""
        # Combine context into a single string
        context_text = "\n".join(context)
        user_message = (
            f"<context>\n{context_text}\n</context>\n"
            f"<question>\n{query}\n</question>"
        )

        return invoke_ai(system_message=SYSTEM_PROMPT, user_message=user_message)
