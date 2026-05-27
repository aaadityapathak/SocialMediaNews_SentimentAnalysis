import os
from dotenv import load_dotenv
import urllib3
from elasticsearch import Elasticsearch
from elasticsearch.helpers import scan, parallel_bulk
from tqdm import tqdm

# Load environment variables
load_dotenv()

# Mute local TLS warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# 1. CONFIGURATION
# ==========================================
ES_HOST = os.getenv("ELASTIC_HOST", "https://localhost:9200")
ES_API_KEY = os.getenv("ELASTIC_API_KEY")

SOURCE_INDEX = os.getenv("INDEX_NAME", "gdelt-events")
TARGET_INDEX = f"gdelt-index"  # We will create a fresh index

USEFUL_COLUMNS = [
    # Core Metadata & High-Resolution Time
    "GlobalEventID",
    "Day",
    "DateAdded",
    "SourceURL",
    # Actors
    "Actor1Name",
    "Actor1CountryCode",
    "Actor2Name",
    "Actor2CountryCode",
    # Action & Classification
    "EventCode",
    "EventRootCode",
    "QuadClass",
    # Location (Action-focused)
    "ActionGeo_Fullname",
    "ActionGeo_Lat",
    "ActionGeo_Long",
    "ActionGeo_CountryCode",
    # ALL GDELT Metrics & Impact
    "GoldsteinScale",
    "NumMentions",
    "NumSources",
    "NumArticles",
    "AvgTone",
    # GKG Context & Deep Sentiment Enrichments
    "GKG_THEMES",
    "GKG_PERSONS",
    "GKG_ORGANIZATIONS",
    "GKG_TONE",
]


# ==========================================
# 2. DATA PIPELINE GENERATOR
# ==========================================
def generate_clean_records(client):
    """
    Scans the old index but ONLY downloads the specific columns we want to keep.
    """
    results = scan(
        client=client,
        index=SOURCE_INDEX,
        query={"query": {"match_all": {}}},
        _source=USEFUL_COLUMNS,
        size=5000,  # BUMPED UP: Fetch 5000 records at a time to feed the writers faster
        scroll="15m",
    )

    for doc in results:
        yield {
            "_op_type": "index",
            "_index": TARGET_INDEX,
            "_id": doc["_id"],
            "_source": doc["_source"],
        }


# ==========================================
# 3. EXECUTION
# ==========================================
if __name__ == "__main__":
    print(f"Connecting to Elasticsearch at {ES_HOST}...")
    es_client = Elasticsearch(
        ES_HOST, api_key=ES_API_KEY, verify_certs=False, request_timeout=120
    )

    # 1. Create the new index with BLAZING FAST bulk-upload settings
    if not es_client.indices.exists(index=TARGET_INDEX):
        print(f"Creating fresh index: '{TARGET_INDEX}'...")
        es_client.indices.create(
            index=TARGET_INDEX,
            settings={
                "index.refresh_interval": "-1",  # Pause background search processing
                "index.number_of_replicas": 0,  # Pause data replication
            },
        )

    # 2. Get total documents for the progress bar
    total_docs = es_client.count(index=SOURCE_INDEX)["count"]
    print(f"Found {total_docs} documents to migrate and clean.")

    # 3. Stream from the old index and parallel upload to the new one
    print("Initiating Parallel Migration...")
    success_count = 0

    for success, info in tqdm(
        parallel_bulk(
            client=es_client,
            actions=generate_clean_records(es_client),
            thread_count=12,
            chunk_size=1500,
            queue_size=24,  # NEW: Doubles the memory queue so threads never starve
            raise_on_error=False,
        ),
        total=total_docs,
        desc="Migrating & Cleaning",
    ):
        if success:
            success_count += 1
        else:
            print(f"\nFailed to migrate document: {info}")

    print("-" * 50)
    print(
        f"SUCCESS: Successfully cleaned and migrated {success_count} documents to '{TARGET_INDEX}'."
    )

    # 4. Turn search processing and replicas back on!
    print("Restoring optimal search settings to the new index...")
    es_client.indices.put_settings(
        index=TARGET_INDEX,
        settings={
            "index.refresh_interval": "1s",
            "index.number_of_replicas": 1,
        },
    )
    print("Migration completely finished!")
