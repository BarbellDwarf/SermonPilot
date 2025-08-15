#!/usr/bin/env python

"""
Script to explore SermonAudio API methods and data structures
"""

import os
import pprint

import sermonaudio
from sermonaudio.node.requests import Node

# Pretty printer for better output
pp = pprint.PrettyPrinter(indent=2)


def explore_node_methods():
    """List all available Node API methods."""
    print("\n=== Available Node API Methods ===")
    methods = [method for method in dir(Node) if not method.startswith('_')]

    # Group by operation type
    get_methods = [m for m in methods if m.startswith('get_')]
    create_methods = [m for m in methods if m.startswith('create_')]
    update_methods = [m for m in methods if m.startswith('update_')]
    delete_methods = [m for m in methods if m.startswith('delete_')]
    other_methods = [m for m in methods if not any(m.startswith(p) for p in ['get_', 'create_', 'update_', 'delete_'])]

    print("\nGET methods:")
    for method in sorted(get_methods):
        print(f"  - Node.{method}()")

    print("\nCREATE methods:")
    for method in sorted(create_methods):
        print(f"  - Node.{method}()")

    print("\nUPDATE methods:")
    for method in sorted(update_methods):
        print(f"  - Node.{method}()")

    print("\nDELETE methods:")
    for method in sorted(delete_methods):
        print(f"  - Node.{method}()")

    print("\nOTHER methods:")
    for method in sorted(other_methods):
        print(f"  - Node.{method}()")


def explore_sermon_object(sermon):
    """Explore the structure of a sermon object."""
    print("\n=== Sermon Object Structure ===")

    # List all attributes
    attrs = [attr for attr in dir(sermon) if not attr.startswith('_')]

    print(f"\nSermon ID: {sermon.sermon_id}")
    print(f"\nAttributes ({len(attrs)}):")

    for attr in sorted(attrs):
        try:
            value = getattr(sermon, attr)
            # Skip methods
            if callable(value):
                continue

            # Format value for display
            if value is None:
                display = "None"
            elif isinstance(value, (str, int, float, bool)):
                display = repr(value)
            elif isinstance(value, (list, tuple)):
                display = f"{type(value).__name__} with {len(value)} items"
            elif isinstance(value, dict):
                display = f"dict with {len(value)} keys"
            else:
                display = f"{type(value).__name__} object"

            print(f"  {attr:<25} : {display}")
        except Exception as e:
            print(f"  {attr:<25} : <Error: {e}>")


def explore_media_object(sermon):
    """Explore the media object structure."""
    print("\n=== Media Object Structure ===")

    if not hasattr(sermon, 'media') or not sermon.media:
        print("No media object found")
        return

    media = sermon.media
    attrs = [attr for attr in dir(media) if not attr.startswith('_')]

    print(f"\nMedia Attributes ({len(attrs)}):")

    for attr in sorted(attrs):
        try:
            value = getattr(media, attr)
            if callable(value):
                continue

            print(f"\n  {attr}:")

            if isinstance(value, list) and value:
                print(f"    List with {len(value)} items")
                # Explore first item
                first_item = value[0]
                item_attrs = [a for a in dir(first_item) if not a.startswith('_')]
                print("    First item attributes:")
                for item_attr in sorted(item_attrs):
                    try:
                        item_value = getattr(first_item, item_attr)
                        if not callable(item_value):
                            print(f"      - {item_attr}: {repr(item_value)[:100]}")
                    except:
                        pass
            elif value:
                print(f"    {type(value).__name__}: {repr(value)[:100]}")
        except Exception as e:
            print(f"  {attr}: <Error: {e}>")


def test_sermon_update_methods(sermon_id):
    """Test different update methods."""
    print("\n=== Testing Update Methods ===")

    # List potential update methods
    update_methods = [
        'update_sermon',
        'update_sermon_info',
        'update_sermon_metadata',
        'update_sermon_media',
        'upload_sermon_media',
        'upload_audio',
        'set_sermon_keywords',
        'set_sermon_description',
    ]

    print("\nChecking for update methods:")
    for method_name in update_methods:
        if hasattr(Node, method_name):
            method = getattr(Node, method_name)
            print(f"  ✓ Node.{method_name}")
            # Print method signature if available
            if hasattr(method, '__doc__') and method.__doc__:
                doc_lines = method.__doc__.strip().split('\n')
                if doc_lines:
                    print(f"    {doc_lines[0]}")
        else:
            print(f"  ✗ Node.{method_name} (not found)")


def main():
    """Main exploration function."""
    # Load API key
    api_key = os.getenv('SERMONAUDIO_API_KEY') or input("Enter SermonAudio API key: ")
    broadcaster_id = os.getenv('SERMONAUDIO_BROADCASTER_ID') or input("Enter Broadcaster ID: ")

    sermonaudio.set_api_key(api_key)

    print(f"\nExploring SermonAudio API for broadcaster: {broadcaster_id}")

    # 1. List available methods
    explore_node_methods()

    # 2. Get a sample sermon
    print("\n\n=== Fetching Sample Sermon ===")
    try:
        response = Node.get_sermons(
            broadcaster_id=broadcaster_id,
            page_size=1
        )

        if response.results:
            sermon = response.results[0]
            sermon_id = sermon.sermon_id
            print(f"Found sermon: {sermon_id}")

            # 3. Explore sermon structure
            explore_sermon_object(sermon)

            # 4. Get detailed sermon info
            print("\n\n=== Fetching Detailed Sermon Info ===")
            detailed_sermon = Node.get_sermon(sermon_id)

            # 5. Explore media structure
            explore_media_object(detailed_sermon)

            # 6. Test update methods
            test_sermon_update_methods(sermon_id)

            # 7. Check for specific methods
            print("\n\n=== Checking Specific Methods ===")

            # Method documentation
            if hasattr(Node, 'update_sermon'):
                print("\nNode.update_sermon documentation:")
                print(Node.update_sermon.__doc__)

            # Try to find media upload methods
            print("\n\nSearching for media-related methods:")
            media_methods = [m for m in dir(Node) if 'media' in m.lower() or 'audio' in m.lower() or 'upload' in m.lower()]
            for method in sorted(media_methods):
                if not method.startswith('_'):
                    print(f"  - Node.{method}")

        else:
            print("No sermons found")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
