#!/usr/bin/env python3
import os, time
from dotenv import load_dotenv
from collector import NetworkCollector
from normalizer import NetworkNormalizer
from versioner import NetworkVersionizer

load_dotenv(".env")

def main():
    collector = NetworkCollector(os.getenv("NETBOX_URL"), os.getenv("NETBOX_TOKEN"))
    normalizer = NetworkNormalizer()
    versioner = NetworkVersionizer()
    while True:
        collected_data = collector.collect_all()
        normalized_data = normalizer.normalize(collected_data)
        versioner.save_snapshots_per_server_with_diff(normalized_data)
        timeout = int(os.getenv("TIME_SEC"))
        print(f"Ожидание {timeout} sec до следующего запуска...")
        time.sleep(timeout)

if __name__ == "__main__":
    main()
