#!/usr/bin/env python3
"""
Test script for the repo-map functionality
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from shell_server_cross_platform import RepoMapper, TREE_SITTER_AVAILABLE

def test_repo_mapper():
    print("Testing RepoMapper...")
    print(f"Tree-sitter available: {TREE_SITTER_AVAILABLE}")
    
    # Test in current directory
    repo_mapper = RepoMapper(".")
    print(f"Available languages: {list(repo_mapper.languages.keys())}")
    
    # Generate repo map
    result = repo_mapper.generate_repo_map()
    print("\nRepo Map Result:")
    print("=" * 50)
    print(result)

if __name__ == "__main__":
    test_repo_mapper()