"""Simple polling worker placeholder. Review execution is synchronous in the MVP API path.
This entrypoint is reserved for moving parsing and review jobs to durable background execution.
"""
import time
from sigillum.config import get_settings

def main():
    settings=get_settings()
    print(f"Sigillum worker scaffold started for environment={settings.app_env}.")
    print("No queued jobs are consumed yet; API review path remains synchronous in this build.")
    try:
        while True: time.sleep(30)
    except KeyboardInterrupt:
        print("Worker stopped.")

if __name__=="__main__": main()
