import os

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic

from agent.mcp_client import (
    search_restaurants,
    check_availability,
    get_alternative_times,
)


load_dotenv()

api_key = os.getenv("ANTHROPIC_API_KEY")

if not api_key:
    raise ValueError("ANTHROPIC_API_KEY is not set in the .env file.")


llm = ChatAnthropic(
    model="claude-sonnet-4-5",
    temperature=0,
    max_tokens=1024,
)


tools = [
    search_restaurants,
    check_availability,
    get_alternative_times,
]


llm_with_tools = llm.bind_tools(tools)