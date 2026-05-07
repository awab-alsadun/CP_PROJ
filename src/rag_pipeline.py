from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Dict, List, Optional
import time

from src.interface import (
    BaseDatastore,
    BaseIndexer,
    BaseRetriever,
    BaseResponseGenerator,
    BaseEvaluator,
    EvaluationResult,
)


@dataclass
class RAGPipeline:
    """Main RAG pipeline that orchestrates all components."""

    datastore: BaseDatastore
    indexer: BaseIndexer
    retriever: BaseRetriever
    response_generator: BaseResponseGenerator
    evaluator: Optional[BaseEvaluator] = None

    def reset(self) -> None:
        """Reset the datastore."""
        self.datastore.reset()

    def add_documents(self, documents: List[str]) -> None:
        """Index a list of documents."""
        start = time.perf_counter()

        items = self.indexer.index(documents)
        self.datastore.add_items(items)

        duration = time.perf_counter() - start
        print(f"✅ Added {len(items)} items to the datastore.")
        print(f"⏱ Indexing Time: {duration:.4f} seconds\n")

    def process_query(self, query: str) -> str:
        total_start = time.perf_counter()

        # 🔎 Retrieval Timing
        retrieval_start = time.perf_counter()
        search_results = self.retriever.search(query)
        retrieval_time = time.perf_counter() - retrieval_start

        print(f"✅ Found {len(search_results)} results for query: {query}")
        print(f"⏱ Retrieval Time: {retrieval_time:.4f} seconds\n")

        # ⚠ Comment this out if chunks are large (printing slows system)
        # for i, result in enumerate(search_results):
        #     print(f"🔍 Result {i+1}: {result}\n")

        # 🤖 Response Generation Timing
        generation_start = time.perf_counter()
        response = self.response_generator.generate_response(query, search_results)
        generation_time = time.perf_counter() - generation_start

        print(f"⏱ Generation Time: {generation_time:.4f} seconds")

        total_time = time.perf_counter() - total_start
        print(f"🚀 Total Query Time: {total_time:.4f} seconds\n")

        return response

    def evaluate(
        self, sample_questions: List[Dict[str, str]]
    ) -> List[EvaluationResult]:

        questions = [item["question"] for item in sample_questions]
        expected_answers = [item["answer"] for item in sample_questions]

        print("\n🚀 Starting Evaluation...\n")
        eval_total_start = time.perf_counter()

        with ThreadPoolExecutor(max_workers=10) as executor:
            results: List[EvaluationResult] = list(
                executor.map(
                    self._evaluate_single_question,
                    questions,
                    expected_answers,
                )
            )

        eval_total_time = time.perf_counter() - eval_total_start

        for i, result in enumerate(results):
            result_emoji = "✅" if result.is_correct else "❌"
            print(f"{result_emoji} Q {i+1}: {result.question}")
            print(f"Response: {result.response}")
            print(f"Expected Answer: {result.expected_answer}")
            print(f"Reasoning: {result.reasoning}")
            print("--------------------------------")

        number_correct = sum(result.is_correct for result in results)
        print(f"✨ Total Score: {number_correct}/{len(results)}")
        print(f"⏱ Total Evaluation Time: {eval_total_time:.4f} seconds\n")

        return results

    def _evaluate_single_question(
        self, question: str, expected_answer: str
    ) -> EvaluationResult:

        if self.evaluator is None:
            raise ValueError("Evaluator is not provided.")

        start = time.perf_counter()

        response = self.process_query(question)

        eval_start = time.perf_counter()
        result = self.evaluator.evaluate(question, response, expected_answer)
        eval_time = time.perf_counter() - eval_start

        total_time = time.perf_counter() - start

        print(f"⏱ Evaluation Time (LLM grading): {eval_time:.4f} seconds")
        print(f"⏱ Total Question Time: {total_time:.4f} seconds\n")

        return result

