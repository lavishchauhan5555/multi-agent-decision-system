from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
import os
from graph.tools import get_mcp_tools

async def build_agent(tools):
    llm = HuggingFaceEndpoint(
        repo_id="meta-llama/Llama-3.1-8B-Instruct",
        task="text-generation",
        temperature=0.7,
        max_new_tokens=2048
    )

    model_hf = ChatHuggingFace(llm=llm)

    model_genai = ChatGoogleGenerativeAI(
        model='gemini-2.5-flash',
        temperature=0.1,    # low temp for math
        max_output_tokens=1500,
        )

    
    grok_llm = ChatOpenAI(
       api_key=os.getenv("XAI_API_KEY"),
       base_url="https://api.groq.com/openai/v1",
       model="llama-3.3-70b-versatile",
       temperature=0.4,
       max_tokens=2048
    )


    return (
        None,
        model_hf.bind_tools(tools),
        model_genai.bind_tools(tools),
        grok_llm.bind_tools(tools),
    )