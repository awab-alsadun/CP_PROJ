from typing import List
from src.interface.base_response_generator import BaseResponseGenerator
from src.util.invoke_ai import invoke_ai


SYSTEM_PROMPT = """
Use the provided context to provide a concise answer to the user's question.
If you cannot find the answer in the context, say so. Do not make up information. dont speak too much,
be concise and to the point. Always use the provided context to answer the question. 
If the answer is not in the context, say "I don't know". 
Do not provide any information that is not in the context.
only answer in 2 sentences.
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
