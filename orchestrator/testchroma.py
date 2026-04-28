# check_chroma.py
import chromadb
from pathlib import Path

CHROMA_PATH = Path(".chroma")
COLLECTION_NAME = "decision_lab"

client = chromadb.PersistentClient(path=str(CHROMA_PATH))
collection = client.get_or_create_collection(COLLECTION_NAME)

print("Total documents:", collection.count())

data = collection.get(
    limit=10,
    include=["documents", "metadatas"]
)

for i, doc in enumerate(data["documents"]):
    print("\n--- Document", i + 1, "---")
    print("Metadata:", data["metadatas"][i])
    print("Text:", doc[:500])