import os
from pymongo import MongoClient
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(env_path)

def get_client():
    mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI") or "mongodb://localhost:27017/"
    return MongoClient(mongo_uri, tlsAllowInvalidCertificates=True, tlsAllowInvalidHostnames=True)

def inspect():
    client = get_client()
    db_name = os.getenv("MONGO_DB", "stance-dashboard")
    db = client[db_name]
    print(f"DB: {db_name}")
    print(f"Collections: {db.list_collection_names()}")

    # Sample some collections
    for coll in ["structured-user-reports", "classification", "prognosis", "patient-metadata"]:
        if coll in db.list_collection_names():
            count = db[coll].count_documents({})
            print(f"  - {coll}: {count} docs")
            if count > 0:
                sample = db[coll].find_one()
                print(f"    Sample keys: {list(sample.keys())}")

if __name__ == "__main__":
    inspect()
