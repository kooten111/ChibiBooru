"""
Phase 4 Verification Test
Tests that the tag repository extraction was successful.
"""

def test_imports():
    """Test that all modules can be imported without circular dependencies."""
    print("Testing imports...")

    # Test models.py imports
    import models
    print("✓ models.py imported successfully")

    # Test tag_repository imports
    from repositories import tag_repository
    print("✓ tag_repository imported successfully")

    # Test that all tag functions are accessible from models
    assert hasattr(models, 'get_tag_counts'), "get_tag_counts not found"
    assert hasattr(models, 'reload_tag_counts'), "reload_tag_counts not found"
    assert hasattr(models, 'get_all_tags_sorted'), "get_all_tags_sorted not found"
    assert hasattr(models, 'recategorize_misplaced_tags'), "recategorize_misplaced_tags not found"
    assert hasattr(models, 'rebuild_categorized_tags_from_relations'), "rebuild_categorized_tags_from_relations not found"
    assert hasattr(models, 'add_implication'), "add_implication not found"
    assert hasattr(models, 'get_implications_for_tag'), "get_implications_for_tag not found"
    assert hasattr(models, 'apply_implications_for_image'), "apply_implications_for_image not found"
    assert hasattr(models, 'update_image_tags'), "update_image_tags not found"
    assert hasattr(models, 'update_image_tags_categorized'), "update_image_tags_categorized not found"
    print("✓ All tag functions accessible from models.py")

    # Test that functions are callable
    assert callable(models.get_tag_counts), "get_tag_counts not callable"
    assert callable(models.update_image_tags), "update_image_tags not callable"
    assert callable(models.add_implication), "add_implication not callable"
    print("✓ All tag functions are callable")

    # Test that tag_repository functions are also directly accessible
    assert hasattr(tag_repository, 'get_tag_counts'), "get_tag_counts not in tag_repository"
    assert hasattr(tag_repository, 'update_image_tags'), "update_image_tags not in tag_repository"
    print("✓ Tag functions accessible from tag_repository module")

    print("\n✓ All import tests passed!")
    return True


def test_no_circular_imports():
    """Test that there are no circular import issues."""
    print("\nTesting for circular imports...")

    import sys
    import importlib

    # Clear any cached imports
    if 'models' in sys.modules:
        del sys.modules['models']
    if 'repositories.tag_repository' in sys.modules:
        del sys.modules['repositories.tag_repository']

    # Import in order that would expose circular dependency
    import models
    from repositories import tag_repository

    # Try calling a function that uses models.data_lock
    # This will fail if there's a circular import issue
    assert callable(tag_repository.get_tag_counts)

    print("✓ No circular imports detected")
    return True


def test_backward_compatibility():
    """Test that the API remains backward compatible."""
    print("\nTesting backward compatibility...")

    import models

    # All these functions should be accessible from models.py as before
    functions = [
        'get_tag_counts',
        'reload_tag_counts',
        'get_all_tags_sorted',
        'recategorize_misplaced_tags',
        'rebuild_categorized_tags_from_relations',
        'add_implication',
        'get_implications_for_tag',
        'apply_implications_for_image',
        'update_image_tags',
        'update_image_tags_categorized',
    ]

    for func_name in functions:
        assert hasattr(models, func_name), f"{func_name} not accessible from models"
        assert callable(getattr(models, func_name)), f"{func_name} not callable"

    print(f"✓ All {len(functions)} functions remain backward compatible")
    return True


def main():
    """Run all verification tests."""
    print("=" * 60)
    print("Phase 4: Tag Repository Extraction - Verification Tests")
    print("=" * 60)

    tests = [
        test_imports,
        test_no_circular_imports,
        test_backward_compatibility,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            failed += 1
            print(f"✗ {test.__name__} failed: {e}")

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == '__main__':
    import sys
    success = main()
    sys.exit(0 if success else 1)
