"""
OpenRouter LLM Executor

This executor uses OpenRouter API to access various large language models
to answer questions provided in the task.
"""
# Setup path before imports - DO NOT REORDER
import sys
from pathlib import Path
_r = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_r))
sys.path.insert(0, str(_r / "worker"))
sys.path.insert(0, str(_r / "orchestrator"))

from mloc_sdk.worker import WorkerSDK
from mloc_sdk.base import BaseExecutor, ExecutionError
from typing import Any, Dict
import os
import requests
import json


class OpenRouterExecutor(BaseExecutor):
    """
    An executor that uses OpenRouter to access LLMs for question answering.
    
    Task Input Format:
        {
            "question": "Your question here",
            "model": "openai/gpt-3.5-turbo",  # Optional, defaults to gpt-3.5-turbo
            "temperature": 0.7,  # Optional
            "max_tokens": 1000,  # Optional
            "system_prompt": "You are a helpful assistant."  # Optional
        }
    
    Returns:
        {
            "status": "success",
            "question": "The original question",
            "answer": "The model's response",
            "model": "Model used",
            "usage": {...}  # Token usage info
        }
    """

    taskType = "openrouter-llm"
    description = "Use OpenRouter API to access LLMs for question answering"
    version = "1.0.0"
    requires_gpu = False

    def __init__(self, api_key: str = None):
        """
        Initialize the OpenRouter executor.
        
        Args:
            api_key: OpenRouter API key. If not provided, will try to read from
                    OPENROUTER_API_KEY environment variable.
        """
        super().__init__()
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.base_url = "https://aiclub.v1.hetu.org/v1"
        
        if not self.api_key:
            raise ValueError(
                "OpenRouter API key required. Set OPENROUTER_API_KEY environment "
                "variable or pass api_key to constructor."
            )

    def prepare(self) -> None:
        """Verify API key works by making a test request."""
        try:
            response = requests.get(
                f"{self.base_url}/models",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                },
                timeout=10
            )
            if response.status_code == 401:
                raise ExecutionError("Invalid OpenRouter API key")
            print(f"✓ OpenRouter API key validated")
        except requests.exceptions.RequestException as e:
            print(f"Warning: Could not validate API key: {e}")

    def execute(self, task_spec: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
        """
        Execute the LLM query using OpenRouter.
        
        Args:
            task_spec: Task specification containing the question and parameters
            output_dir: Directory to save outputs
            
        Returns:
            Dictionary with the answer and metadata
        """
        # Extract input parameters
        input_data = task_spec.get("input", {})
        question = input_data.get("message") or input_data.get("question")
        
        if not question:
            raise ExecutionError("No 'question' provided in task input")
        
        # Get optional parameters with defaults
        model = input_data.get("model", "gemini-2.0-flash")
        temperature = input_data.get("temperature", 0.7)
        max_tokens = input_data.get("max_tokens", 10000)
        system_prompt = input_data.get(
            "system_prompt", 
            "You are a helpful assistant."
        )
        
        print(f"Processing question with model {model}: {question[:100]}...")
        
        # Prepare the API request
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question}
        ]
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/mloc-network",  # Optional
            "X-Title": "MLOC OpenRouter Executor",  # Optional
        }
        
        data = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        try:
            # Make the API request
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=data,
                timeout=120  # 2 minute timeout for long responses
            )
            
            if response.status_code != 200:
                error_msg = f"OpenRouter API error: {response.status_code} - {response.text}"
                raise ExecutionError(error_msg)
            
            result = response.json()
            
            # Extract the answer
            answer = result["choices"][0]["message"]["content"]
            usage = result.get("usage", {})
            
            # Prepare output
            output = {
                "status": "success",
                "question": question,
                "answer": answer,
                "model": model,
                "usage": {
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                },
                "parameters": {
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
            }
            
            # Save detailed response
            self.save_json(output_dir / "response.json", output)
            self.save_text(output_dir / "answer.txt", answer)
            self.save_text(output_dir / "question.txt", question)
            
            print(f"✓ Successfully generated response ({usage.get('total_tokens', 0)} tokens)")
            
            return output
            
        except requests.exceptions.Timeout:
            raise ExecutionError("Request timed out waiting for OpenRouter response")
        except requests.exceptions.RequestException as e:
            raise ExecutionError(f"Request failed: {str(e)}")
        except (KeyError, IndexError) as e:
            raise ExecutionError(f"Unexpected response format: {str(e)}")


if __name__ == "__main__":
    # Get API key from environment
    api_key = os.getenv("OPENROUTER_API_KEY")
    
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY environment variable not set")
        print("Please set it with: export OPENROUTER_API_KEY='your-api-key'")
        sys.exit(1)
    
    # Create SDK
    sdk = WorkerSDK(
        worker_id="openrouter-worker-001",
        orchestrator_url="ws://localhost:8000/ws/worker",
        description="OpenRouter LLM executor for question answering",
        log_level="INFO"
    )
    
    # Register executor
    executor = OpenRouterExecutor(api_key=api_key)
    sdk.register_executor(executor)
    
    # Start worker
    print("Starting OpenRouter LLM worker...")
    print(f"Registered executor: {executor.taskType}")
    sdk.run()
