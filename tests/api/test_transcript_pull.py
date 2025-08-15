from sermonaudio.node.requests import Node

SERMON_ID = "1212241923147168"

def print_transcript_and_fields(sermon_id):
    details = Node.get_sermon(sermon_id)
    print(f"Sermon ID: {sermon_id}")
    if hasattr(details, 'full_text') and details.full_text:
        print("Transcript (full_text):\n", details.full_text)
    else:
        print("No transcript in 'full_text'. Dumping all fields:")
        for attr in dir(details):
            if not attr.startswith('_'):
                try:
                    value = getattr(details, attr)
                    if not callable(value):
                        print(f"  {attr}: {repr(value)[:200]}")
                except Exception as e:
                    print(f"  {attr}: <Error: {e}>")

if __name__ == "__main__":
    print_transcript_and_fields(SERMON_ID)
