import glob
import json
import os
from typing import List
from src.rag_pipeline import RAGPipeline
from create_parser import create_parser
from src.impl import Datastore, Indexer, Retriever, ResponseGenerator, Evaluator


DEFAULT_SOURCE_PATH = "sample_data/source/"
DEFAULT_EVAL_PATH = "sample_data/eval/sample_questions.json"


def create_pipeline() -> RAGPipeline:
    """Create and return a new RAG Pipeline instance with all components."""
    datastore = Datastore()
    indexer = Indexer()
    retriever = Retriever(datastore=datastore)
    response_generator = ResponseGenerator()
    evaluator = Evaluator()
    return RAGPipeline(datastore, indexer, retriever, response_generator, evaluator)


def main():
    parser = create_parser()  # Create the CLI parser
    args = parser.parse_args()
    pipeline = create_pipeline()

    # Change to the script directory to resolve relative paths correctly
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    # Process source paths and eval path
    source_path = args.path if args.path else DEFAULT_SOURCE_PATH
    eval_path = args.eval_file if args.eval_file else DEFAULT_EVAL_PATH
    document_paths = get_files_in_directory(source_path)

    # Execute commands
    if args.command in ["reset", "run"]:
        print("🗑️  Resetting the database...")
        pipeline.reset()

    if args.command in ["add", "run"]:
        print(f"🔍 Adding documents: {', '.join(document_paths)}")
        pipeline.add_documents(document_paths)

    if args.command in ["evaluate", "run"]:
        print(f"📊 Evaluating using questions from: {eval_path}")
        with open(eval_path, "r") as file:
            sample_questions = json.load(file)
        results = pipeline.evaluate(sample_questions)
        
        # Save to JSON if output flag is provided
        if hasattr(args, 'output') and args.output:
            save_results_to_json(results, args.output)
            print(f"💾 Results saved to: {args.output}")

    if args.command == "query":
        print(f"✨ Response: {pipeline.process_query(args.prompt)}")


def get_files_in_directory(source_path: str) -> List[str]:
    if os.path.isfile(source_path):
        return [source_path]
    return glob.glob(os.path.join(source_path, "*"))


def save_results_to_json(results, output_path: str) -> None:
    """Save evaluation results to a JSON file."""
    json_results = {
        "total": len(results),
        "correct": sum(1 for r in results if r.is_correct),
        "accuracy": sum(1 for r in results if r.is_correct) / len(results) if results else 0,
        "results": [
            {
                "question": r.question,
                "response": r.response,
                "expected_answer": r.expected_answer,
                "is_correct": r.is_correct,
                "reasoning": r.reasoning,
            }
            for r in results
        ]
    }
    
    with open(output_path, "w") as f:
        json.dump(json_results, f, indent=2)



if __name__ == "__main__":
    main()
