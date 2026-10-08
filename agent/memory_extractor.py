from typing import Optional

from pydantic import BaseModel, Field

from agent.claude import llm


class MemoryUpdate(BaseModel):
    """
    Represents information that may be worth remembering
    about a user.
    """

    memory_type: Optional[str] = Field(
        default=None,
        description=(
            "The type of memory. Currently supported: "
            "'preference' or 'profile'."
        ),
    )

    memory_key: Optional[str] = Field(
        default=None,
        description=(
            "The specific memory being remembered. "
            "Supported keys are: preferred_cuisine, "
            "preferred_location, preferred_restaurant, "
            "typical_party_size, budget_preference, "
            "user_name."
        ),
    )

    memory_value: Optional[str] = Field(
        default=None,
        description="The value of the memory.",
    )


def extract_memory(user_message: str) -> MemoryUpdate:
    """
    Extract one persistent memory from the latest user message.

    Returns an empty MemoryUpdate when there is nothing
    appropriate to remember.
    """

    prompt = f"""
You are the long-term memory extraction system for Reseva,
an AI restaurant reservation agent.

Your job is to identify information from the user's latest
message that is useful to remember across future conversations.

Latest user message:

{user_message}


ONLY REMEMBER INFORMATION THAT IS INTENDED TO BE USEFUL
ACROSS FUTURE RESTAURANT-RELATED CONVERSATIONS.

Currently supported memories:

1. preferred_cuisine

Examples:
"I love Italian food."
→ memory_type = preference
→ memory_key = preferred_cuisine
→ memory_value = Italian

"I usually go for Japanese restaurants."
→ memory_type = preference
→ memory_key = preferred_cuisine
→ memory_value = Japanese


2. preferred_location

Examples:
"I normally eat around Mayfair."
→ memory_type = preference
→ memory_key = preferred_location
→ memory_value = Mayfair

"I prefer restaurants in Manchester city centre."
→ memory_type = preference
→ memory_key = preferred_location
→ memory_value = Manchester city centre


3. preferred_restaurant

Examples:
"Bella Italia Mayfair is my favourite restaurant."
→ memory_type = preference
→ memory_key = preferred_restaurant
→ memory_value = Bella Italia Mayfair

"My preferred restaurant is Bella Italia Mayfair."
→ memory_type = preference
→ memory_key = preferred_restaurant
→ memory_value = Bella Italia Mayfair

"I always like booking Bella Italia Mayfair."
→ memory_type = preference
→ memory_key = preferred_restaurant
→ memory_value = Bella Italia Mayfair


4. typical_party_size

Examples:
"I usually go out with two people."
→ memory_type = preference
→ memory_key = typical_party_size
→ memory_value = 2

"I normally book tables for four."
→ memory_type = preference
→ memory_key = typical_party_size
→ memory_value = 4


5. budget_preference

Examples:
"I prefer affordable restaurants."
→ memory_type = preference
→ memory_key = budget_preference
→ memory_value = affordable

"I normally look for mid-range restaurants."
→ memory_type = preference
→ memory_key = budget_preference
→ memory_value = moderate

"I don't mind expensive restaurants."
→ memory_type = preference
→ memory_key = budget_preference
→ memory_value = expensive


6. user_name

The user's name may be remembered for personalization.

Examples:
"My name is Uche."
→ memory_type = profile
→ memory_key = user_name
→ memory_value = Uche

"You can call me Uche."
→ memory_type = profile
→ memory_key = user_name
→ memory_value = Uche


IMPORTANT RULES:

1. Only extract information that the user explicitly
   indicates should be remembered or that clearly represents
   a persistent preference, habit, or profile detail.

2. Do NOT remember temporary booking details.

For example:

"Book me an Italian restaurant tomorrow."
→ return null

"Find me somewhere at 7pm tonight."
→ return null

"I want a restaurant for 4 people tomorrow."
→ return null


3. A restaurant preference should normally be expressed as
   something the user likes, prefers, normally does, usually
   chooses, or explicitly asks Reseva to remember.

4. If the user explicitly says "remember", "my preferred",
   "my favourite", "I usually", "I normally", or similar
   language, treat the information as persistent memory.

5. Do not infer a preferred restaurant simply because the
   user booked that restaurant once.

6. Do not infer a preferred location simply because the user
   booked a restaurant in that location once.

7. Do not invent information.

8. Only use these memory keys:

- preferred_cuisine
- preferred_location
- preferred_restaurant
- typical_party_size
- budget_preference
- user_name

9. Use memory_type "preference" for:

- preferred_cuisine
- preferred_location
- preferred_restaurant
- typical_party_size
- budget_preference

10. Use memory_type "profile" for:

- user_name

11. If there is no useful long-term memory in the message,
    return null for all fields.

12. Return only ONE memory from the latest message.

13. If the user provides both their name and a preference,
    prioritize the most explicit restaurant preference.

14. Do not store personal information unrelated to the
    user's name or restaurant-related preferences.

Return the structured memory update.
"""

    return llm.with_structured_output(
        MemoryUpdate
    ).invoke(prompt)