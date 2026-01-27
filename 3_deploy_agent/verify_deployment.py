import json
import sys
import urllib.request
import urllib.error
from urllib.parse import urlparse

def test_deployment():
    # Path to the local agent.json (updated by deploy.sh)
    LOCAL_AGENT_JSON = "remote_a2a/remote_time_agent/.well-known/agent.json"

    print(f"Loading local configuration from {LOCAL_AGENT_JSON}...")
    try:
        with open(LOCAL_AGENT_JSON, 'r') as f:
            local_config = json.load(f)
    except FileNotFoundError:
        print(f"Error: Could not find {LOCAL_AGENT_JSON}. Have you run deploy.sh?")
        sys.exit(1)

    base_url = local_config.get("url")
    if not base_url:
        print("Error: 'url' field missing in agent.json")
        sys.exit(1)

    # Ensure trailing slash for base construction, though typically it has it
    if not base_url.endswith('/'):
        base_url += '/'

    print(f"Target Agent Base URL: {base_url}")

    if "localhost" in base_url:
        print("\n[WARNING] The URL in agent.json is pointing to localhost.")
        print("This suggests verify_deployment.py is running before deploy.sh has successfully updated the file,")
        print("or you are testing a local instance.")
        response = input("Continue? (y/n): ")
        if response.lower() != 'y':
            sys.exit(0)

    # 1. Test Root Endpoint (Health Check)
    # The base_url includes /a2a/remote_time_agent/, we want the server root for the health check
    parsed_url = urlparse(base_url)
    root_url = f"{parsed_url.scheme}://{parsed_url.netloc}/"
    
    print(f"\n1. Testing Root Endpoint: {root_url}")
    try:
        with urllib.request.urlopen(root_url) as response:
            status = response.getcode()
            content = response.read().decode('utf-8')
            print(f"   Status: {status}")
            print(f"   Content: {content}")
            
            if status == 200 and "Remote Time Agent A2A Server is running" in content:
                print("   [PASS] Root endpoint is healthy.")
            else:
                print("   [FAIL] Root endpoint returned unexpected response.")
    except urllib.error.URLError as e:
        print(f"   [FAIL] Could not connect to root endpoint: {e}")

    # 2. Test Agent Card Endpoint
    agent_card_url = f"{base_url}.well-known/agent.json"
    print(f"\n2. Testing Agent Card Endpoint: {agent_card_url}")
    
    try:
        req = urllib.request.Request(agent_card_url)
        # Verify that we can fetch it without Auth (it should be open)
        with urllib.request.urlopen(req) as response:
            status = response.getcode()
            remote_card_data = json.loads(response.read().decode('utf-8'))
            
            print(f"   Status: {status}")
            
            # Validation
            if remote_card_data.get("name") == local_config.get("name"):
                print(f"   [PASS] Agent name matches: {remote_card_data.get('name')}")
            else:
                print(f"   [FAIL] Agent name mismatch! Remote: {remote_card_data.get('name')}, Local: {local_config.get('name')}")

            if remote_card_data.get("url") == base_url:
                print(f"   [PASS] Remote agent.json correctly self-references: {base_url}")
            else:
                print(f"   [FAIL] Remote agent.json URL mismatch! Remote says: {remote_card_data.get('url')}")

            # Check DCR config
            caps = remote_card_data.get("capabilities", {{}})
            exts = caps.get("extensions", [])
            dcr_correct = False
            for ext in exts:
                if "setup-dcr" in ext.get("uri", ""):
                    target = ext.get("params", {{}}).get("target_url", "")
                    if parsed_url.netloc in target:
                        dcr_correct = True
                        print(f"   [PASS] DCR Target URL correctly points to host: {target}")
            
            if not dcr_correct:
                 print("   [WARN] Could not verify DCR target_url configuration.")

    except urllib.error.HTTPError as e:
        print(f"   [FAIL] HTTP Error: {e.code} - {e.reason}")
    except urllib.error.URLError as e:
        print(f"   [FAIL] URL Error: {e.reason}")
    except json.JSONDecodeError:
        print("   [FAIL] Response was not valid JSON.")

    print("\n------------------------------------------------")
    print("Note: Actual A2A protocol endpoints require OAuth.")
    print("      This script only validates public reachability and configuration.")

if __name__ == "__main__":
    test_deployment()
