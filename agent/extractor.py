from datetime import date
from typing import Optional

from pydantic import BaseModel, Field

from agent.claude import llm


class ReservationUpdate(BaseModel):
    location: Optional[str] = Field(default=None)
    cuisine: Optional[str] = Field(default=None)

    selected_restaurant_id: Optional[str] = Field(
        default=None,
        description="The ID of the restaurant the user explicitly selected.",
    )

    # CREATE
    booking_requested: Optional[bool] = Field(
        default=None,
        description=(
            "True only when the user explicitly asks Reseva "
            "to make a new reservation."
        ),
    )

    # MODIFY
    modification_requested: Optional[bool] = Field(
        default=None,
        description=(
            "True only when the user explicitly asks Reseva "
            "to modify an existing reservation."
        ),
    )

    # CANCEL
    cancellation_requested: Optional[bool] = Field(
        default=None,
        description=(
            "True only when the user explicitly asks Reseva "
            "to cancel an existing reservation."
        ),
    )

    reservation_id_to_modify: Optional[str] = Field(
        default=None,
        description=(
            "The existing Reseva reservation ID to modify or cancel, "
            "only when explicitly provided or clearly identified."
        ),
    )

    # Existing booking details
    date: Optional[str] = Field(
        default=None,
        description="Reservation date in YYYY-MM-DD format.",
    )

    time: Optional[str] = Field(
        default=None,
        description="Reservation time in HH:MM 24-hour format.",
    )

    party_size: Optional[int] = Field(default=None)
    budget: Optional[float] = Field(default=None)

    # Modification details
    modification_date: Optional[str] = Field(
        default=None,
        description="New date requested for an existing reservation.",
    )

    modification_time: Optional[str] = Field(
        default=None,
        description="New time requested for an existing reservation.",
    )

    modification_party_size: Optional[int] = Field(
        default=None,
        description="New party size requested for an existing reservation.",
    )


def extract_reservation_update(
    user_message: str,
    current_state: dict,
) -> ReservationUpdate:

    today = date.today().isoformat()

    available_restaurants = current_state.get(
        "available_restaurants",
        [],
    )

    availability_results = current_state.get(
        "availability_results",
        [],
    )

    prompt = f"""
Extract reservation information from the user's latest message.

Today's date is {today}.

Current reservation state:

Location:
{current_state.get("location")}

Cuisine:
{current_state.get("cuisine")}

Date:
{current_state.get("date")}

Time:
{current_state.get("time")}

Party size:
{current_state.get("party_size")}

Budget:
{current_state.get("budget")}

Currently selected restaurant:
{current_state.get("selected_restaurant_id")}

Current reservation ID:
{current_state.get("reservation_id_to_modify")}


Restaurants previously found:

{available_restaurants}


Availability results:

{availability_results}


Latest user message:

{user_message}


RULES
-----

GENERAL EXTRACTION
------------------

1. Only extract information that is explicitly provided
   or clearly implied by the latest user message.

2. Do not remove or overwrite existing information.

3. If a value is not present in the latest message,
   return null for that field.

4. Convert relative dates such as "tomorrow" into
   YYYY-MM-DD.

5. Convert times such as "7pm" into HH:MM 24-hour format.

6. "7pm" means "19:00".

7. "7:30pm" means "19:30".


RESTAURANT SELECTION
--------------------

8. If the user explicitly selects a restaurant, return
   its restaurant ID.

For example:

"Book Bella Italia"
→ selected_restaurant_id = "rest-001"

"Let's go with Bella Italia Mayfair"
→ selected_restaurant_id = "rest-001"

"Book La Tavola"
→ selected_restaurant_id = "rest-002"

"I want Bella Italia"
→ selected_restaurant_id = "rest-001"

9. RESTAURANT SELECTION PRIORITY
-------------------------------

If the current reservation state already contains a
selected_restaurant_id, preserve that restaurant ID.

Do NOT replace the existing selected_restaurant_id with
another restaurant based on availability results.

If the user explicitly named a restaurant in the current
request, that restaurant takes priority over any other
restaurant returned by search_restaurants.

For example:

Current state:
selected_restaurant_id = "rest-002"

Availability results:
rest-001 = available
rest-002 = unavailable

User request:
"I want La Tavola."

Result:
selected_restaurant_id = "rest-002"

Never change it to rest-001 merely because rest-001 is
available.


10. Only set selected_restaurant_id when the user actually
   selects a restaurant OR when the user says something
   like "book it" and the current state contains exactly
   one clearly suitable available restaurant.


10. Never invent a restaurant ID.

Only use restaurant IDs that appear in:

- the restaurants previously found, or
- the availability results.


BOOKING / CREATE INTENT
-----------------------

11. If the user says:

"book it"

"yes, book it"

"go ahead"

"make the booking"

"reserve it"

or similar language referring to the previously discussed
restaurant, determine whether the current state contains
exactly one suitable available restaurant.


12. When resolving "book it":

- If current_state already contains a selected_restaurant_id,
  ALWAYS preserve that restaurant ID.

- Only use availability_results to select a restaurant when
  there is no selected_restaurant_id.

- If there is no selected restaurant and exactly ONE restaurant
  is available, select that restaurant's ID.

- If more than one restaurant is available, do NOT choose one
  automatically.

- If no restaurant is available, do NOT select one.


13. If more than one restaurant is available, do NOT
    choose one automatically.

The user must choose the restaurant.


14. If no restaurant is available, do NOT select one.


15. If the user says "book it" and there is already a
    selected_restaurant_id in the current state, preserve
    that restaurant ID.


16. Set booking_requested to true ONLY when the user
    explicitly asks Reseva to make a new reservation.

Examples:

"Book Bella Italia"
→ booking_requested = true

"Yes, book it"
→ booking_requested = true

"Go ahead and make the reservation"
→ booking_requested = true

"Please make the booking"
→ booking_requested = true

"Reserve it"
→ booking_requested = true


17. Searching, browsing, comparing or checking availability
    is NOT a booking request.

Examples:

"Which restaurants are available?"
→ booking_requested = false

"Show me some options"
→ booking_requested = false

"Is Bella Italia available?"
→ booking_requested = false


18. If the user explicitly asks to book but does not name
    a restaurant:

- First use the already selected restaurant if one exists.
- Otherwise look at availability_results.
- If exactly one restaurant is available, select it.
- If multiple restaurants are available, leave
  selected_restaurant_id as null.
- If no restaurants are available, leave it as null.


MODIFICATION / UPDATE INTENT
----------------------------

19. Set modification_requested = true when the user
    explicitly wants to change an existing reservation.

Examples:

"Change my reservation to 8pm."
→ modification_requested = true
→ modification_time = "20:00"

"Move my booking to tomorrow."
→ modification_requested = true
→ modification_date = tomorrow's date

"Change my reservation to 4 people."
→ modification_requested = true
→ modification_party_size = 4

"Change reservation res-10001 to 8pm."
→ modification_requested = true
→ reservation_id_to_modify = "res-10001"
→ modification_time = "20:00"


20. For modification requests, only extract the values
    that the user actually wants to change.

For example:

"Change my booking to 8pm."

should produce:

modification_requested = true
modification_time = "20:00"

Do NOT invent a new date or party size.


21. If the user says "change my booking" but does not
    specify what should change:

modification_requested = true

and:

modification_date = null
modification_time = null
modification_party_size = null


22. If the user explicitly provides a reservation ID
    for a modification, preserve that exact ID.


23. Never invent a reservation ID.


CANCELLATION INTENT
-------------------

24. Set cancellation_requested = true when the user
    explicitly asks to cancel an existing reservation.

Examples:

"Cancel my reservation."
→ cancellation_requested = true

"I want to cancel my booking."
→ cancellation_requested = true

"Cancel reservation res-10001."
→ cancellation_requested = true
→ reservation_id_to_modify = "res-10001"


25. If the user explicitly provides a reservation ID
    for cancellation, preserve that exact ID.


26. Never invent a reservation ID.


INTENT SAFETY
-------------

27. CREATE, MODIFY and CANCEL are mutually exclusive.

Only set the intent explicitly expressed in the latest
user message.


28. MODIFY and CANCEL must never set booking_requested
    to true.


29. A question about an existing reservation is NOT
    automatically a modification or cancellation.

Example:

"What's my reservation time?"

→ modification_requested = false
→ cancellation_requested = false


30. Never interpret the following as cancellation unless
    the user clearly asks to cancel:

"Can I change my booking?"

This is a modification request.


31. Never interpret the following as a new booking:

"Change my booking."

This is a modification request.


32. Never claim that a reservation has been created,
    modified, or cancelled.

This extractor only identifies the user's intent
and requested state changes.

33. Never invent restaurant IDs.

34. Never invent reservation IDs.

35. Return only the structured reservation update.
"""

    return llm.with_structured_output(
        ReservationUpdate
    ).invoke(prompt)