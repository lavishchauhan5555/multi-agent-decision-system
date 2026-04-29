# db/mongo.py
import os
from pymongo import MongoClient
import motor.motor_asyncio

_sync_client = None
_async_client = None


def get_db_name():
    return os.getenv("DB_NAME", "autonomous_decision_lab")


def get_sync_client():
    global _sync_client
    if _sync_client is None:
        uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        _sync_client = MongoClient(uri)
    return _sync_client


def get_sync_collection(name: str):
    mapping = {
        "sessions": "sessions",
        "prompts": "prompts",
        "notes": "notes",
        "skills": "skills",
        "leaderboards": "leaderboards",
        "users": "users",
    }

    col_name = mapping.get(name, name)
    return get_sync_client()[get_db_name()][col_name]


def get_async_client():
    global _async_client
    if _async_client is None:
        uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        _async_client = motor.motor_asyncio.AsyncIOMotorClient(uri)
    return _async_client


async def get_collection(name: str):
    mapping = {
        "sessions": "sessions",
        "prompts": "prompts",
        "notes": "notes",
        "skills": "skills",
        "leaderboards": "leaderboards",
        "users": "users",
    }

    col_name = mapping.get(name, name)
    return get_async_client()[get_db_name()][col_name]