import os
graphviz_path = r'C:\Program Files\Graphviz\bin'
os.environ["PATH"] += os.pathsep + graphviz_path

from diagrams import Cluster, Diagram, Edge
from diagrams.custom import Custom

with Diagram("예제파일", show=False):
    with Cluster("Frontend"):
        retriever = Custom("retriever", "res/retrieval.png")
        res = Custom("response", "res/response.png")
        query = Custom("query", "res/question.png")
        Custom("user", "res/user.png") >> retriever >> query
        query - Edge(color="black", style="dashed") - Custom("context", "res/context.png") >> Edge(color="balck", style="collected") >> Custom("prompt", "res/prompt.png") >> Edge(color="balck", style="collected") >> Custom("LLM", "res/llm.png") >> Edge(color="balck", style="collected") >> res
    
    with Cluster("Backend"):
        unstructured_data = Custom("unstructured_data", "res/unstructured_data.png")
        structured_data = Custom("structured_data", "res/structured_data.png")
        web = Custom("website", "res/website.png")
        vector_store = Custom("vector_store", "res/vector_store.png")
        doc_loader = Custom("Document Loader", "res/doc_loader.png")
        doc_loader << Edge(color="black") << unstructured_data
        doc_loader << Edge(color="black") << structured_data
        doc_loader << Edge(color="black") << web
        vector_store << Custom("embedding", "res/embedding.png") << Custom("chunking", "res/chunking.png") << Custom("splitter", "res/split.png") << doc_loader
        retriever << vector_store
        retriever >> vector_store