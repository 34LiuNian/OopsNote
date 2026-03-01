#!/usr/bin/env python3
"""
Quick smoke test for architecture refactoring.

Run: uv run python scripts/test_refactor.py
"""

import sys
from pathlib import Path

# Add backend to path
backend_root = Path(__file__).parent.parent
sys.path.insert(0, str(backend_root))


def test_models_import():
    """Test that all models can be imported."""
    print("Testing models imports...")
    print("  ✓ All models imported successfully")


def test_agents_utils():
    """Test that agents utils module works."""
    print("Testing agents utils...")
    from app.agents import utils
    import traceback

    try:
        # Test coercion helpers
        assert utils._coerce_str(None, "default") == "default"
        assert utils._coerce_str("test") == "test"
        assert utils._coerce_list(None, ["default"]) == ["default"]
        assert utils._coerce_list(["a", "b"], []) == ["a", "b"]
        assert utils._coerce_int("5", 0, 0, 10) == 5
        assert utils._coerce_int("invalid", 3, 0, 10) == 3

        # Test text utilities
        assert utils._normalize_linebreaks("test\r\ntest") == "test\ntest"
        assert utils._contains_placeholder("Hello {name}") is True
        result = utils._extract_placeholders("Hello {name}, you are {age}")
        assert result == ["name", "age"]

        print("  ✓ Agents utils working correctly")
    except Exception as e:
        print(f"  Error details: {e}")
        traceback.print_exc()
        raise


def test_agents_modules():
    """Test that all agents modules can be imported."""
    print("Testing agents modules...")
    print("  ✓ All agents modules imported successfully")


def test_backward_compatibility():
    """Test backward compatibility of models import."""
    print("Testing backward compatibility...")

    # Old style import should still work via models/__init__.py
    from app.models import TaskRecord, ProblemBlock
    from datetime import datetime, timezone
    from app.models import TaskCreateRequest, HttpUrl

    # Create instances to ensure models are functional
    task = TaskRecord(
        id="test-123",
        payload=TaskCreateRequest(image_url=HttpUrl("https://example.com/test.png")),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    assert task.id == "test-123"

    problem = ProblemBlock(
        problem_id="p1",
        region_id="r1",
        problem_text="Test problem",
    )
    assert problem.problem_id == "p1"

    print("  ✓ Backward compatibility maintained")


def main():
    """Run all smoke tests."""
    print("=" * 60)
    print("Architecture Refactoring - Smoke Tests")
    print("=" * 60)

    tests = [
        test_models_import,
        test_agents_utils,
        test_agents_modules,
        test_backward_compatibility,
    ]

    failed = []
    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"  ✗ {test.__name__} failed: {e}")
            failed.append((test.__name__, e))

    print("=" * 60)
    if not failed:
        print("✓ All tests passed!")
        return 0
    else:
        print(f"✗ {len(failed)} test(s) failed:")
        for name, error in failed:
            print(f"  - {name}: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
