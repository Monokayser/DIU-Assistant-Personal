import os
import google.generativeai as genai

class GeminiEmbeddings:
    def __init__(self, api_key: str = None, model_name: str = "models/text-embedding-004"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if self.api_key:
            genai.configure(api_key=self.api_key)
        self.model_name = model_name

    def embed_query(self, text: str):
        result = genai.embed_content(
            model=self.model_name,
            content=text,
            task_type="retrieval_query"
        )
        return result['embedding']

    def embed_documents(self, texts: list[str]):
        result = genai.embed_content(
            model=self.model_name,
            content=texts,
            task_type="retrieval_document"
        )
        return result['embedding']
