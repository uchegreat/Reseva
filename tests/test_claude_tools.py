from agent.claude import llm_with_tools


response = llm_with_tools.invoke(
    "Find me an Italian restaurant in Mayfair."
)


print("\nClaude response:")
print(response.content)

print("\nTool calls:")
print(response.tool_calls)