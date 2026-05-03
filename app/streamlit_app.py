import streamlit as st
import os
import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent))

from src.ingestion import VisibleContentParser, fetch_page
from src.rag_pipeline import RAGPipeline
from src.agents import (
    AdmissionAgent, 
    CourseAdvisorAgent, 
    ScholarshipAdvisorAgent, 
    GeneralAssistantAgent
)

st.set_page_config(page_title="DIU Assistant", page_icon="🎓", layout="wide")

st.title("🎓 DIU Assistant")
st.markdown("Your official guide to Daffodil International University.")

if "messages" not in st.session_state:
    st.session_state.messages = []

# Sidebar for settings and file upload
with st.sidebar:
    st.header("Settings")
    api_key = st.text_input("Gemini API Key", type="password")
    if api_key:
        os.environ["GEMINI_API_KEY"] = api_key
    
    st.header("Agent Settings")
    agent_type = st.selectbox(
        "Select Specialist Agent",
        ["General Assistant", "Admission Agent", "Course Advisor", "Scholarship Advisor"]
    )
    
    st.header("Document Ingestion")
    uploaded_files = st.file_uploader("Upload DIU Documents", accept_multiple_files=True)
    
    if st.button("Process Documents"):
        if not api_key:
            st.error("Please provide an API Key first.")
        else:
            with st.spinner("Ingesting..."):
                # Initialize pipeline
                pipeline = RAGPipeline(api_key=api_key)
                for uploaded_file in uploaded_files:
                    bytes_data = uploaded_file.read()
                    pipeline.ingest_file(bytes_data, uploaded_file.name)
                st.success("Documents processed and ready!")
                st.session_state.pipeline = pipeline

# Chat Interface
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Ask me anything about DIU"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        if "pipeline" not in st.session_state:
            st.warning("Please upload and process documents first.")
        else:
            with st.spinner(f"{agent_type} is thinking..."):
                # Use pipeline for retrieval and agent for answering
                results = st.session_state.pipeline.retrieve(prompt)
                
                # Initialize selected agent
                if agent_type == "Admission Agent":
                    agent = AdmissionAgent(api_key=api_key)
                elif agent_type == "Course Advisor":
                    agent = CourseAdvisorAgent(api_key=api_key)
                elif agent_type == "Scholarship Advisor":
                    agent = ScholarshipAdvisorAgent(api_key=api_key)
                else:
                    agent = GeneralAssistantAgent(api_key=api_key)
                
                # Convert results to list of dicts for agent
                context_chunks = [
                    {"url": r.chunk.source, "title": r.chunk.title, "text": r.chunk.text}
                    for r in results[:5]
                ]
                
                response = agent.answer_question(prompt, context_chunks)
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
