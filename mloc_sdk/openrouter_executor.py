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
from typing import Any, Dict, List
import os
import requests
import json
import sqlite3
import uuid
from datetime import datetime


class OpenRouterExecutor(BaseExecutor):
    """
    An executor that uses OpenRouter to access LLMs for question answering.
    
    Features:
    - Conversation history management with session_id
    - SQLite database for persistent conversation storage
    - Automatic context window management (keeps last 5000 words)
    
    Task Input Format:
        {
            "question": "Your question here",
            "message": "Alternative to question",
            "session_id": "optional-session-id",  # For continuing conversation
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
            "session_id": "session-identifier",  # For continuing conversation
            "conversation_history": [  # Full conversation history (if exists)
                {"role": "user", "content": "..."},
                {"role": "assistant", "content": "..."},
                ...
            ],
            "model": "Model used",
            "usage": {...}  # Token usage info
        }
    """

    taskType = "openrouter-llm"
    description = "Use OpenRouter API to access LLMs for question answering with conversation history"
    version = "2.0.0"
    requires_gpu = False
    
    # Maximum words to keep in conversation history
    MAX_HISTORY_WORDS = 5000

    def __init__(self, api_key: str = None, db_path: str = None):
        """
        Initialize the OpenRouter executor.
        
        Args:
            api_key: OpenRouter API key. If not provided, will try to read from
                    OPENROUTER_API_KEY environment variable.
            db_path: Path to SQLite database for conversation history.
                    Defaults to './conversation_history.db'
        """
        super().__init__()
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.base_url = "https://aiclub.v1.hetu.org/v1"
        self.db_path = db_path or os.getenv("CONVERSATION_DB_PATH", "./conversation_history.db")
        
        if not self.api_key:
            raise ValueError(
                "OpenRouter API key required. Set OPENROUTER_API_KEY environment "
                "variable or pass api_key to constructor."
            )
        
        # Initialize database
        self._init_database()

    def _init_database(self) -> None:
        """Initialize SQLite database for conversation history."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create conversations table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                model TEXT
            )
        """)
        
        # Create index for faster session_id lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_session_id 
            ON conversations (session_id)
        """)
        
        conn.commit()
        conn.close()
        print(f"✓ Conversation database initialized at {self.db_path}")
    
    def _get_conversation_history(self, session_id: str, max_words: int = None) -> List[Dict[str, str]]:
        """
        Retrieve conversation history for a session.
        
        Args:
            session_id: The session identifier
            max_words: Maximum number of words to retrieve (default: MAX_HISTORY_WORDS)
            
        Returns:
            List of message dictionaries with 'role' and 'content'
        """
        if max_words is None:
            max_words = self.MAX_HISTORY_WORDS
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT role, content FROM conversations
            WHERE session_id = ?
            ORDER BY timestamp ASC
        """, (session_id,))
        
        messages = []
        total_words = 0
        all_messages = cursor.fetchall()
        conn.close()
        
        # Start from the most recent and work backwards, keeping track of word count
        for role, content in reversed(all_messages):
            words = len(content.split())
            if total_words + words > max_words and messages:
                # Stop if adding this message would exceed limit (but always include at least one)
                break
            messages.insert(0, {"role": role, "content": content})
            total_words += words
        
        return messages
    
    def _save_message(self, session_id: str, role: str, content: str, model: str = None) -> None:
        """
        Save a message to conversation history.
        
        Args:
            session_id: The session identifier
            role: Message role ('user', 'assistant', 'system')
            content: Message content
            model: Model used (optional)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO conversations (session_id, role, content, model)
            VALUES (?, ?, ?, ?)
        """, (session_id, role, content, model))
        
        conn.commit()
        conn.close()
    
    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        return str(uuid.uuid4())

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
        Execute the LLM query using OpenRouter with conversation history support.
        
        Args:
            task_spec: Task specification containing the question and parameters
            output_dir: Directory to save outputs
            
        Returns:
            Dictionary with the answer, session_id, and metadata
        """
        # Extract input parameters
        input_data = task_spec.get("input", {})
        question = input_data.get("message") or input_data.get("question")
        
        if not question:
            raise ExecutionError("No 'question' or 'message' provided in task input")
        
        # Get or create session_id
        session_id = input_data.get("session_id")
        is_new_session = session_id is None
        
        if is_new_session:
            session_id = self._generate_session_id()
            print(f"Starting new conversation: {session_id}")
        else:
            print(f"Continuing conversation: {session_id}")
        
        # Get optional parameters with defaults
        model = input_data.get("model", "gemini-2.0-flash")
        temperature = input_data.get("temperature", 0.7)
        max_tokens = input_data.get("max_tokens", 10000)
        system_prompt = input_data.get(
            "system_prompt", 
            "You are a helpful assistant."
        )
        
        print(f"Processing question with model {model}: {question[:100]}...")
        
        # Build messages with conversation history
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add conversation history if continuing a session
        if not is_new_session:
            history = self._get_conversation_history(session_id)
            if history:
                # Filter out system messages from history to avoid duplication
                history = [msg for msg in history if msg["role"] != "system"]
                messages.extend(history)
                print(f"Loaded {len(history)} messages from conversation history")
        
        # Add current user message
        messages.append({"role": "user", "content": question})
        
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
            
            # Save conversation to history
            self._save_message(session_id, "user", question, model)
            self._save_message(session_id, "assistant", answer, model)
            
            # Get updated conversation history (including current exchange)
            conversation_history = self._get_conversation_history(session_id)
            
            # Prepare output
            output = {
                "status": "success",
                "question": question,
                "answer": answer,
                "session_id": session_id,
                "is_new_session": is_new_session,
                "conversation_history": conversation_history,  # Include full conversation history
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
            self.save_text(output_dir / "session_id.txt", session_id)
            
            print(f"✓ Successfully generated response ({usage.get('total_tokens', 0)} tokens)")
            print(f"✓ Session ID: {session_id}")
            
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
    
    # Get worker_id from environment variable, or generate a random UUID if not set
    worker_id = os.getenv("WORKER_ID")
    if not worker_id:
        worker_id = f"openrouter-worker-{uuid.uuid4()}"
        print(f"No WORKER_ID environment variable set, generated: {worker_id}")
    else:
        print(f"Using WORKER_ID from environment: {worker_id}")
    
    # Create SDK
    sdk = WorkerSDK(
        worker_id=worker_id,
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
