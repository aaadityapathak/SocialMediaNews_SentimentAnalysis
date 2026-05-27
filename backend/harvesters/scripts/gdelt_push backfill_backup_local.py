import os
import pandas as pd
import urllib3
import numpy as np
from elasticsearch import Elasticsearch
from elasticsearch import helpers
from tqdm import tqdm

from gdelt_retrieve.schemas import USEFUL_COLUMNS

if __name__ == "__main__":
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    host = os.getenv("ELASTIC_HOST", "https://localhost:9200")
    key = os.getenv("ELASTIC_API_KEY")
    INDEX_NAME = os.getenv("INDEX_NAME", "gdelt-events")

    print("Loading CSV into memory...")
    df = pd.read_csv(
        "data/gdelt/gdelt_backfill_backups/gdelt_backup_20260101_20260510.csv",
        low_memory=False,
    )

    # --- DATAFRAME TIMESTAMP FIX ---
    # Prevents Pandas from interpreting "20260518004500" as scientific float
    if "DateAdded" in df.columns:
        df["DateAdded"] = (
            df["DateAdded"]
            .fillna("")
            .astype(str)
            .str.split(".")
            .str[0]
            .str.ljust(14, "0")
        )

    # --- PANDAS COLUMN FILTERING ---
    cols_to_keep = [c for c in USEFUL_COLUMNS if c in df.columns]
    df = df[cols_to_keep]

    print("Cleaning missing values for JSON compatibility...")
    df = df.replace("nan", np.nan)
    df = df.astype(object).replace({np.nan: None})

    records = df.to_dict(orient="records")

    es_client = Elasticsearch(
        host,
        api_key=key,
        verify_certs=False,
        request_timeout=120,
        max_retries=3,
        retry_on_timeout=True,
    )

    print(f"Initiating MULTI-THREADED upload of {len(records)} records...")

    def generate_actions(data_list, index):
        for record in data_list:
            yield {
                "_index": index,
                "_id": f"{record['GlobalEventID']}_{record.get('SourceURL', '')}",
                "_source": record,
            }

    success_count = 0
    for success, info in tqdm(
        helpers.parallel_bulk(
            client=es_client,
            actions=generate_actions(records, "gdelt-events"),
            thread_count=12,  # Ryzen 7 Optimized
            queue_size=24,
            chunk_size=1500,
            raise_on_error=False,
        ),
        total=len(records),
        desc="Uploading to ES",
    ):
        if success:
            success_count += 1
        else:
            print(f"\nFailed to index document: {info}")

    print(
        f"\nSUCCESS: Multi-threaded batch uploaded {success_count} documents to ES."
    )
