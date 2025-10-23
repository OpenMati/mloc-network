#!/usr/bin/env python3
"""
Test script to verify MLOC SDK functionality without external dependencies.

This script tests the SDK components in isolation:
- BaseExecutor creation
- Decorator executors
- WorkerSDK initialization
- Executor registration
"""
from mloc_sdk.base import ExecutionError
from mloc_sdk import BaseExecutor, WorkerSDK, executor
import sys
from pathlib import Path
import tempfile
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_base_executor():
    """Test basic executor creation and methods."""
    print("Testing BaseExecutor...")

    class TestExecutor(BaseExecutor):
        name = "test-executor"
        description = "Test executor"
        version = "1.0.0"

        def execute(self, task_spec, output_dir):
            return {"status": "success"}

    executor = TestExecutor()
    assert executor.name == "test-executor"
    assert executor.version == "1.0.0"

    # Test execution
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        result = executor.execute({"test": "data"}, output_dir)
        assert result["status"] == "success"

    print("✓ BaseExecutor test passed")


def test_helper_methods():
    """Test executor helper methods."""
    print("Testing helper methods...")

    class HelperTestExecutor(BaseExecutor):
        name = "helper-test"

        def execute(self, task_spec, output_dir):
            # Test save/load JSON
            data = {"key": "value", "number": 42}
            self.save_json(output_dir / "test.json", data)
            loaded = self.load_json(output_dir / "test.json")
            assert loaded == data

            # Test save/load text
            text = "Hello, World!"
            self.save_text(output_dir / "test.txt", text)
            loaded_text = self.load_text(output_dir / "test.txt")
            assert loaded_text == text

            # Test validation
            self.validate_task_spec(task_spec, ["required_field"])

            return {"status": "ok"}

    executor = HelperTestExecutor()

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        result = executor.execute({"required_field": "value"}, output_dir)
        assert result["status"] == "ok"

        # Check files were created
        assert (output_dir / "test.json").exists()
        assert (output_dir / "test.txt").exists()

    print("✓ Helper methods test passed")


def test_decorator_executor():
    """Test decorator-based executor."""
    print("Testing @executor decorator...")

    @executor(name="test-decorator", description="Test", version="1.0.0")
    def test_func(task_spec, output_dir):
        return {"decorator": "works"}

    assert hasattr(test_func, 'name')
    assert test_func.name == "test-decorator"

    with tempfile.TemporaryDirectory() as tmpdir:
        result = test_func.execute({"test": "data"}, Path(tmpdir))
        assert result["decorator"] == "works"

    print("✓ Decorator executor test passed")


def test_execution_error():
    """Test ExecutionError handling."""
    print("Testing ExecutionError...")

    class ErrorExecutor(BaseExecutor):
        name = "error-test"

        def execute(self, task_spec, output_dir):
            if "error" in task_spec:
                raise ExecutionError("Test error")
            return {"status": "ok"}

    executor = ErrorExecutor()

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)

        # Should work fine
        result = executor.execute({}, output_dir)
        assert result["status"] == "ok"

        # Should raise ExecutionError
        try:
            executor.execute({"error": True}, output_dir)
            assert False, "Should have raised ExecutionError"
        except ExecutionError as e:
            assert "Test error" in str(e)

    print("✓ ExecutionError test passed")


def test_worker_sdk():
    """Test WorkerSDK initialization and registration."""
    print("Testing WorkerSDK...")

    class TestExecutor1(BaseExecutor):
        name = "test-1"

        def execute(self, task_spec, output_dir):
            return {"id": 1}

    class TestExecutor2(BaseExecutor):
        name = "test-2"

        def execute(self, task_spec, output_dir):
            return {"id": 2}

    with tempfile.TemporaryDirectory() as tmpdir:
        sdk = WorkerSDK(
            worker_id="test-worker",
            results_dir=Path(tmpdir),
            log_level="ERROR",  # Suppress logs during test
        )

        # Test registration
        sdk.register_executor(TestExecutor1())
        sdk.register_executor(TestExecutor2(), as_default=True)

        # Test listing
        executors = sdk.list_executors()
        assert "test-1" in executors
        assert "test-2" in executors

        # Test retrieval
        exec1 = sdk.get_executor("test-1")
        assert exec1 is not None
        assert exec1.name == "test-1"

        exec2 = sdk.get_executor("test-2")
        assert exec2 is not None
        assert exec2.name == "test-2"

        # Test default executor
        assert sdk._default_executor.name == "test-2"

    print("✓ WorkerSDK test passed")


def test_lifecycle_hooks():
    """Test executor lifecycle hooks."""
    print("Testing lifecycle hooks...")

    lifecycle_log = []

    class LifecycleExecutor(BaseExecutor):
        name = "lifecycle-test"

        def prepare(self):
            lifecycle_log.append("prepare")

        def execute(self, task_spec, output_dir):
            lifecycle_log.append("execute")
            return {"status": "ok"}

        def cleanup(self):
            lifecycle_log.append("cleanup")

        def teardown(self):
            lifecycle_log.append("teardown")

    executor = LifecycleExecutor()

    # Test prepare
    executor.prepare()
    assert "prepare" in lifecycle_log

    # Test execute
    with tempfile.TemporaryDirectory() as tmpdir:
        executor.execute({}, Path(tmpdir))
    assert "execute" in lifecycle_log

    # Test cleanup
    executor.cleanup()
    assert "cleanup" in lifecycle_log

    # Test teardown
    executor.teardown()
    assert "teardown" in lifecycle_log

    print("✓ Lifecycle hooks test passed")


def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("MLOC SDK Test Suite")
    print("=" * 60)
    print()

    tests = [
        test_base_executor,
        test_helper_methods,
        test_decorator_executor,
        test_execution_error,
        test_worker_sdk,
        test_lifecycle_hooks,
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"✗ {test_func.__name__} failed: {e}")
            failed += 1
            import traceback
            traceback.print_exc()
        print()

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
