import os
import sys
import logging

logging.basicConfig(level=logging.INFO)

sys.path.insert(0, "/app")
import rag_ingest as ri

def test_query(query: str, top_k: int = 3):
    print(f"\n{'='*50}\nQuery: {query}\n{'='*50}")
    
    client = ri.get_milvus_client()
    embedder = ri.get_embedder()
    
    collection_name = ri.COLLECTION_NAME
    
    try:
        vec = embedder.get_text_embedding(query)
    except Exception as e:
        print(f"Embedding failed: {e}")
        return

    search_params = {
        "collection_name": collection_name,
        "data": [vec],
        "limit": top_k,
        "output_fields": ["text", "title", "source", "content_type", "url"]
    }

    try:
        results = client.search(**search_params)
        if not results or not results[0]:
            print("No results found.")
            return

        for i, hit in enumerate(results[0], 1):
            entity = hit.get("entity", hit) # Handle different MilvusClient versions
            title = entity.get("title", "No Title")
            source = entity.get("source", "No Source")
            content_type = entity.get("content_type", "text")
            text = entity.get("text", "")
            distance = hit.get("distance", hit.get("score", 0.0))
            
            print(f"\n--- Result {i} (Distance: {distance:.4f}) ---")
            print(f"Source: {source} | Type: {content_type} | Title: {title}")
            print(f"Content:\n{text[:300]}...\n")
    except Exception as e:
        print(f"Search failed: {e}")

if __name__ == "__main__":
    queries = [
        "住院保障具体包含哪些内容？",
        "宏利优越终身保有什么特点？",
        "保单如何分红？"
    ]
    for q in queries:
        test_query(q)
