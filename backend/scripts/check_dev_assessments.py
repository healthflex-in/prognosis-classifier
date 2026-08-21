#!/usr/bin/env python3
from pymongo import MongoClient

DEV_URI = "mongodb+srv://healthflex-dev:FUvgMqSppKigmKHK@healthflex-dev.5kbaq08.mongodb.net/stance-dashboard?retryWrites=true&w=majority"
client = MongoClient(DEV_URI, serverSelectionTimeoutMS=15000)
db = client["stance-dashboard"]

print("\n── Collections and document counts in dev stance-dashboard ──")
for name in sorted(db.list_collection_names()):
    count = db[name].count_documents({})
    print(f"  {name:<40} {count:>6} docs")
print()
