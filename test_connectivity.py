import os
import json
from openai import OpenAI
import google.genai as genai
import time
import sys
import traceback

# Config path
CONFIG_FILE = os.path.join(os.path.expanduser('~'), '.transcription_config.json')

def load_keys():
    if not os.path.exists(CONFIG_FILE):
        print(f"❌ Config file not found at: {CONFIG_FILE}")
        return {}
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Error reading config file: {e}")
        return {}

def test_openai(api_key):
    print("\n--- Testing OpenAI Connectivity ---")
    if not api_key:
        print("[SKIP]: OpenAI API Key not found in config.")
        return

    try:
        client = OpenAI(api_key=api_key)
        print("Creating connectivity test request (gpt-4o-mini) with LARGE payload (10KB)...")
        # Simulate a moderate transcription (approx 10,000 chars)
        large_text = "This is a test sentence. " * 500 
        start = time.time()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "user", "content": f"Please summarize this check: {large_text[:100]}... (ignore the rest)"}
            ],
            max_tokens=10
        )
        duration = time.time() - start
        content = response.choices[0].message.content
        print(f"[SUCCESS] OpenAI Success! Response time: {duration:.2f}s")
        print(f"Response: {content}")
    except Exception as e:
        print("[FAIL] OpenAI Failed!")
        traceback.print_exc()

def test_gemini(api_key):
    print("\n--- Testing Gemini Connectivity ---")
    if not api_key:
        print("[SKIP]: Gemini API Key not found in config.")
        return

    try:
        print("Initializing Gemini client...")
        # Using the same timeout logic as requested/modified in main app if we want strict comparison,
        # but for a simple "hello" it should be fast. Let's set a reasonable 30s timeout.
        client = genai.Client(api_key=api_key, http_options={'timeout': 30})
        
        print("Creating connectivity test request (gemini-2.5-flash)...")
        start = time.time()
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=["Hello, are you online? Reply with 'Yes'."]
        )
        duration = time.time() - start
        
        if response and response.text:
             print(f"[SUCCESS] Gemini Success! Response time: {duration:.2f}s")
             print(f"Response: {response.text}")
        else:
             print("[WARN] Gemini returned no text response.")
    except Exception as e:
        print("[FAIL] Gemini Failed!")
        traceback.print_exc()

def main():
    print(f"Reading keys from: {CONFIG_FILE}")
    keys = load_keys()
    
    openai_key = keys.get('openai')
    gemini_key = keys.get('gemini')
    
    test_openai(openai_key)
    test_gemini(gemini_key)
    
    print("\n--- Connectivity Test Complete ---")

if __name__ == "__main__":
    main()
