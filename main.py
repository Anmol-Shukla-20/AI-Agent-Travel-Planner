from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from agent.agentic_workflow import GraphBuilder
from utils.save_to_document import save_document
from starlette.responses import JSONResponse
import os
import datetime
from dotenv import load_dotenv
from pydantic import BaseModel
load_dotenv()
from langchain_core.messages import HumanMessage, AIMessage
import uuid
from typing import Optional
from utils.json_store import JsonStore

app = FastAPI()

# simple JSON-backed chat store (used by the Streamlit UI)
base_dir = os.path.dirname(os.path.abspath(__file__))
data_dir = os.path.join(base_dir, "data")
os.makedirs(data_dir, exist_ok=True)
store = JsonStore(os.path.join(data_dir, "chats.json"))


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # set specific origins in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
class QueryRequest(BaseModel):
    question: str
    model: Optional[str] = None

# Added new classes
class ChatCreate(BaseModel):
    title: Optional[str] = "New Chat"
    model: Optional[str] = None


class MessageCreate(BaseModel):
    role: str
    content: str

@app.post("/query")
async def query_travel_agent(query:QueryRequest):
    try:
        print(query)
        from agent.agentic_workflow import GraphBuilder 

        model _choice = query.model or "groq"
        graph = GraphBuilder(model_provider=model_choice)
        react_app=graph()
        #react_app = graph.build_graph()

        png_graph = react_app.get_graph().draw_mermaid_png()
        with open("my_graph.png", "wb") as f:
            f.write(png_graph)

        print(f"Graph saved as 'my_graph.png' in {os.getcwd()}")

        detailed_instructions = (
            "Please produce a complete, comprehensive travel plan in Markdown. Include a day-by-day itinerary, "
            "recommended hotels with approximate per-night costs, places of attraction, recommended restaurants with "
            "price ranges, activities, transport options, a detailed cost breakdown, per-day budget, and weather. "
            "Provide two variants if possible: a standard tourist plan and an off-beat plan."
        )

        human = HumanMessage(content=f"{query.question}\n\n{detailed_instructions}")
        messages = {"messages": [human]}
        
        # Assuming request is a pydantic object like: {"question": "your text"}
        messages={"messages": [query.question]}
        output = react_app.invoke(messages)

        # determine a safe log path next to this file(to check)
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        except Exception:
            base_dir = os.getcwd()
        raw_path = os.path.join(base_dir, "last_raw_output.txt")
        err_path = os.path.join(base_dir, "last_error.txt")

        # Invoke the graph runtime and capture any exceptions/outputs to log files
        try:
            output = react_app.invoke(messages)
            try:
                with open(raw_path, "w", encoding="utf-8") as lof:
                    lof.write(repr(output))
            except Exception:
                pass
        except Exception as invoke_exc:
            import traceback
            trace = traceback.format_exc()
            try:
                with open(err_path, "w", encoding="utf-8") as ef:
                    ef.write(trace)
            except Exception:
                pass
            return JSONResponse(status_code=500, content={"error": "invoke_failed", "trace": trace})

        # Robust extraction of text from common response shapes
        final_output = None
        ai_last_message = None
        if isinstance(output, dict):
            if "messages" in output and output["messages"]:
                ai_last_message = output["messages"][-1]
                final_output = getattr(ai_last_message, "content", None) or str(ai_last_message)
            elif "content" in output:
                final_output = output["content"]
            else:
                final_output = str(output)
        elif hasattr(output, "content"):
            ai_last_message = output
            final_output = output.content
        else:
            final_output = str(output)
