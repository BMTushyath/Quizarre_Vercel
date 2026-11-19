import sys

def read_log():
    try:
        # Try UTF-16 first (Windows PowerShell pipe default)
        with open('load_test_results.log', 'r', encoding='utf-16le') as f:
            print(f.read())
    except UnicodeDecodeError:
        # Fallback to UTF-8
        with open('load_test_results.log', 'r', encoding='utf-8') as f:
            print(f.read())

if __name__ == "__main__":
    read_log()
