import socket
import json
import time

POOL_HOST = 'stratum.slushpool.com'
POOL_PORT = 3333
WORKER_NAME = 'example.worker'
WORKER_PASSWORD = 'password'

def run_miner():

    # 1. Create a TCP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    print(f"[*] Connecting to {POOL_HOST}:{POOL_PORT}...")

    try:
        sock.connect((POOL_HOST, POOL_PORT))
        print("[*] Connected to the mining pool.")
    except Exception as e:
        print(f"[!] Connection failed: {e}")
        return
    
    # 2. Send the subscription message
    subscribe_msg = {"id": 1, "method": "mining.subscribe", "params": []}
    sock.sendall((json.dumps(subscribe_msg) + '\n').encode())
    response = sock.recv(4096).decode()
    print(f"[*] Server response:\n {response}")

    # 3. Send the authorization message
    auth_msg = {
        "id": 2,
        "method": "mining.authorize",
        "params": [WORKER_NAME, WORKER_PASSWORD]
    }
    sock.sendall((json.dumps(auth_msg) + '\n').encode('utf-8'))

    # 4. Listen for mining jobs
    print("[*] Listening for mining jobs...")
    start_time = time.time()
    while time.time() - start_time < 15: 
        try:
            data = sock.recv(2048).decode()
            if not data:
                break
                
            for line in data.split('\n'):
                if line:
                    data_json = json.loads(line)
                    method = data_json.get('method')
                    
                    if method == 'mining.notify':
                        print("\n[!] NEW JOB RECEIVED!")
                        print(f"    Job ID: {data_json['params'][0]}")
                        print(f"    Prev Hash: {data_json['params'][1]}")
                        # This is where we would start the SHA256 loop
                    else:
                        print(f"[<] Message: {line}")
                        
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error parsing data: {e}")
            break

    print("[*] Closing connection.")
    sock.close()

if __name__ == "__main__":
    run_miner()