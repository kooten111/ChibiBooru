#!/usr/bin/env python3
"""
Clear Tag Deltas Script

This script clears tag deltas from the database. Use this to clean up
incorrectly recorded automated changes that were mistakenly treated as
manual modifications.

WARNING: This will permanently delete delta records. Use with caution.
"""

import sys
import os

# Add parent directory to path so we can import from the project
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import models


def main():
    print("Tag Delta Clearing Utility")
    print("=" * 60)
    print()
    print("This script will clear tag deltas from the database.")
    print("Tag deltas are used to preserve manual user edits across database rebuilds.")
    print()
    print("Options:")
    print("  1. Clear ALL deltas (use this to clean up automated changes)")
    print("  2. Clear deltas for a specific image")
    print("  3. Cancel")
    print()

    choice = input("Enter your choice (1-3): ").strip()

    if choice == "1":
        # Clear all deltas
        print()
        print("WARNING: This will delete ALL tag deltas from the database.")
        print("This cannot be undone!")
        print()
        confirm = input("Are you sure? Type 'yes' to confirm: ").strip().lower()

        if confirm == "yes":
            count = models.clear_all_deltas()
            print(f"✓ Successfully cleared {count} tag deltas.")
        else:
            print("Operation cancelled.")

    elif choice == "2":
        # Clear deltas for specific image
        print()
        filepath = input("Enter the image filepath (e.g., 'b4a/image.jpg'): ").strip()

        if not filepath:
            print("Error: Filepath cannot be empty.")
            return

        count = models.clear_deltas_for_image(filepath)
        if count > 0:
            print(f"✓ Successfully cleared {count} tag deltas for {filepath}.")
        else:
            print(f"No deltas found for {filepath}.")

    elif choice == "3":
        print("Operation cancelled.")

    else:
        print("Invalid choice.")


if __name__ == "__main__":
    main()
