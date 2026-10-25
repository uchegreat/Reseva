import { useRef, useState, type FormEvent } from "react";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

type InterruptValue = {
  type?: string;
  restaurant?: string;
  restaurant_id?: string;
  date?: string;
  time?: string;
  party_size?: number;
  message?: string;
};

type ApiResponse = {
  thread_id: string;
  status: string;
  message: string;
  data?: Record<string, unknown> | null;
};

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ??
  (import.meta.env.DEV ? "http://127.0.0.1:8000" : "")
).replace(/\/$/, "");

function getMessageText(content: unknown): string {
  if (typeof content === "string") {
    return content;
  }

  if (Array.isArray(content)) {
    return content
      .map((item) => {
        if (typeof item === "string") {
          return item;
        }

        if (item && typeof item === "object") {
          const value = item as Record<string, unknown>;

          if (typeof value.text === "string") {
            return value.text;
          }

          if (typeof value.content === "string") {
            return value.content;
          }
        }

        return "";
      })
      .filter(Boolean)
      .join("");
  }

  if (content && typeof content === "object") {
    const value = content as Record<string, unknown>;

    if (typeof value.text === "string") {
      return value.text;
    }

    if (typeof value.content === "string") {
      return value.content;
    }
  }

  return "";
}

function isInternalMessage(text: string): boolean {
  const normalized = text.trim().toLowerCase();

  return (
    normalized.startsWith("reseva long-term user preferences:") ||
    normalized.startsWith("reseva execution plan:") ||
    normalized.includes("current user request:")
  );
}

function renderMessageText(text: string) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) =>
    part.length > 4 && part.startsWith("**") && part.endsWith("**") ? (
      <strong key={index}>{part.slice(2, -2)}</strong>
    ) : (
      part
    ),
  );
}

function isToolMessage(value: Record<string, unknown>): boolean {
  const type = String(value.type ?? "").toLowerCase();
  const role = String(value.role ?? "").toLowerCase();

  return (
    ["tool", "tool_result", "tool_call", "function"].includes(type) ||
    role === "tool" ||
    (Array.isArray(value.tool_calls) && value.tool_calls.length > 0) ||
    Boolean(value.tool_call_id)
  );
}

function looksLikeToolResult(text: string): boolean {
  const trimmed = text.trim();

  if (!trimmed.startsWith("{") || !trimmed.endsWith("}")) {
    return false;
  }

  try {
    const parsed = JSON.parse(trimmed);

    if (!parsed || typeof parsed !== "object") {
      return false;
    }

    const value = parsed as Record<string, unknown>;

    return [
      "available",
      "restaurant_id",
      "reservation_id",
      "party_size",
      "booking_id",
      "slots",
      "availability",
    ].some((key) => key in value);
  } catch {
    return false;
  }
}

/*
 * Extract customer-facing assistant messages from the
 * final state returned by FastAPI/LangGraph.
 */
function extractAssistantMessages(
  data: Record<string, unknown> | null | undefined
): string[] {
  if (!data) {
    return [];
  }

  const rawMessages = data.messages;

  if (!Array.isArray(rawMessages)) {
    return [];
  }

  const results: string[] = [];

  for (const item of rawMessages) {
    if (!item || typeof item !== "object") {
      continue;
    }

    const value = item as Record<string, unknown>;

    if (isToolMessage(value)) {
      continue;
    }

    const type = String(value.type ?? "").toLowerCase();
    const role = String(value.role ?? "").toLowerCase();

    if (
      ["human", "user", "tool", "tool_result", "tool_call"].includes(type) ||
      ["user", "human", "tool"].includes(role)
    ) {
      continue;
    }

    const text = getMessageText(value.content).trim();

    if (
      !text ||
      isInternalMessage(text) ||
      looksLikeToolResult(text)
    ) {
      continue;
    }

    if (!results.includes(text)) {
      results.push(text);
    }
  }

  return results;
}

function extractInterrupt(
  data: Record<string, unknown> | null | undefined
): InterruptValue | null {
  if (!data) {
    return null;
  }

  const rawInterrupts = data.__interrupt__;

  if (!Array.isArray(rawInterrupts) || rawInterrupts.length === 0) {
    return null;
  }

  const first = rawInterrupts[0];

  if (!first || typeof first !== "object") {
    return null;
  }

  const item = first as Record<string, unknown>;

  const rawValue =
    item.value && typeof item.value === "object"
      ? (item.value as Record<string, unknown>)
      : item;

  if (typeof rawValue.message !== "string") {
    return null;
  }

  return rawValue as InterruptValue;
}

async function callApi(
  path: string,
  body: Record<string, unknown>
): Promise<ApiResponse> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  const result = await response.json().catch(() => null);

  if (!response.ok) {
    const detail =
      result &&
      typeof result === "object" &&
      typeof result.detail === "string"
        ? result.detail
        : "The reservation service could not process your request.";

    throw new Error(detail);
  }

  return result as ApiResponse;
}

function App() {
  const [input, setInput] = useState("");
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [interruptValue, setInterruptValue] =
    useState<InterruptValue | null>(null);
  const [emailInput, setEmailInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isResponding, setIsResponding] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const approvalInProgress = useRef(false);

  const addAssistantMessages = (
    data: Record<string, unknown> | null | undefined
  ) => {
    const messages = extractAssistantMessages(data);

    if (messages.length === 0) {
      return;
    }

    setChatMessages((previous) => {
      const updated = [...previous];

      for (const content of messages) {
        if (
          updated.some(
            (message) =>
              message.role === "assistant" &&
              message.content === content
          )
        ) {
          continue;
        }

        updated.push({
          id: crypto.randomUUID(),
          role: "assistant",
          content,
        });
      }

      return updated;
    });
  };

  const handleSubmit = async (
    event: FormEvent<HTMLFormElement>
  ) => {
    event.preventDefault();

    const message = input.trim();

    if (!message || isLoading || isResponding || interruptValue) {
      return;
    }

    setErrorMessage("");
    setInput("");
    setIsLoading(true);

    setChatMessages((previous) => [
      ...previous,
      {
        id: crypto.randomUUID(),
        role: "user",
        content: message,
      },
    ]);

    /*
     * LangGraph requires a UUID-formatted thread ID.
     * Reuse the same ID throughout this conversation.
     */
    const currentThreadId = threadId ?? crypto.randomUUID();

    setThreadId(currentThreadId);

    try {
      const result = await callApi("/api/v1/chat", {
        thread_id: currentThreadId,
        user_id: "web-user",
        message,
      });

      addAssistantMessages(result.data);

      const pendingInterrupt = extractInterrupt(result.data);

      if (result.status === "approval_required" && pendingInterrupt) {
        setInterruptValue(pendingInterrupt);
      } else if (result.status === "approval_required") {
        setErrorMessage(
          result.message || "Booking approval is required, but its details were unavailable."
        );
      } else if (
        extractAssistantMessages(result.data).length === 0 &&
        result.message
      ) {
        setChatMessages((previous) => [
          ...previous,
          {
            id: crypto.randomUUID(),
            role: "assistant",
            content: result.message,
          },
        ]);
      }
    } catch (error) {
      console.error("Reseva request failed:", error);

      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Something went wrong. Please try again."
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleApproval = async (decision: boolean | string) => {
    if (!threadId || !interruptValue || approvalInProgress.current) {
      return;
    }

    approvalInProgress.current = true;
    setIsResponding(true);
    setErrorMessage("");

    try {
      const result = await callApi(
        `/api/v1/chat/${encodeURIComponent(threadId)}/resume`,
        { approval: decision }
      );

      setInterruptValue(null);
      addAssistantMessages(result.data);

      const nextInterrupt = extractInterrupt(result.data);

      if (result.status === "approval_required" && nextInterrupt) {
        setInterruptValue(nextInterrupt);
      } else if (
        extractAssistantMessages(result.data).length === 0 &&
        result.message
      ) {
        setChatMessages((previous) => [
          ...previous,
          {
            id: crypto.randomUUID(),
            role: "assistant",
            content: result.message,
          },
        ]);
      }
    } catch (error) {
      console.error("Reseva approval failed:", error);

      setErrorMessage(
        error instanceof Error
          ? error.message
          : "We could not process your booking decision."
      );
    } finally {
      approvalInProgress.current = false;
      setIsResponding(false);
    }
  };

  const approvalLabels = (() => {
    switch (interruptValue?.type) {
      case "modification_confirmation":
        return { yes: "Confirm change", no: "Keep original" };
      case "cancellation_confirmation":
        return { yes: "Yes, cancel it", no: "Keep reservation" };
      default:
        return { yes: "Confirm booking", no: "Cancel" };
    }
  })();

  const isEmailQuestion =
    interruptValue?.type === "email_request" ||
    interruptValue?.type === "modification_email";

  return (
    <main className="min-h-screen bg-[#f7f5f0] text-[#171717] flex flex-col items-center px-6">
      <header className="pt-12 sm:pt-16">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-black text-xl font-semibold text-white">
            R
          </div>

          <h1 className="text-3xl sm:text-4xl font-semibold tracking-[0.3em]">
            ESEVA
          </h1>
        </div>
      </header>

      <section className="flex flex-1 w-full max-w-3xl flex-col items-center justify-center -mt-10">
        {chatMessages.length > 0 && (
          <div className="mb-6 w-full max-w-2xl space-y-3">
            {chatMessages.map((message) => (
              <div
                key={message.id}
                className={`flex ${
                  message.role === "user"
                    ? "justify-end"
                    : "justify-start"
                }`}
              >
                <div
                  className={`max-w-[85%] whitespace-pre-line rounded-2xl px-4 py-3 text-sm leading-6 ${
                    message.role === "user"
                      ? "bg-black text-white"
                      : "border border-black/5 bg-white shadow-sm"
                  }`}
                >
                  {renderMessageText(message.content)}
                </div>
              </div>
            ))}

            {(isLoading || isResponding) && (
              <div
                className="flex justify-start"
                role="status"
                aria-label="ResEva is thinking"
              >
                <div className="flex items-center gap-1.5 rounded-2xl border border-black/5 bg-white px-4 py-4 shadow-sm">
                  {[0, 150, 300].map((delay) => (
                    <span
                      key={delay}
                      className="h-2 w-2 animate-bounce rounded-full bg-black/40"
                      style={{ animationDelay: `${delay}ms` }}
                    />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {interruptValue?.message && (
          <div className="mb-6 w-full max-w-2xl rounded-2xl border border-black/5 bg-white p-5 shadow-sm">
            <p className="text-sm leading-6">
              {interruptValue.message}
            </p>

            {(interruptValue.restaurant ||
              interruptValue.date ||
              interruptValue.time ||
              interruptValue.party_size) && (
              <div className="mt-4 rounded-xl bg-[#f7f5f0] p-4 text-sm">
                {interruptValue.restaurant && (
                  <p>
                    <span className="font-medium">Restaurant:</span>{" "}
                    {interruptValue.restaurant}
                  </p>
                )}

                {interruptValue.party_size && (
                  <p>
                    <span className="font-medium">Guests:</span>{" "}
                    {interruptValue.party_size}
                  </p>
                )}

                {interruptValue.date && (
                  <p>
                    <span className="font-medium">Date:</span>{" "}
                    {interruptValue.date}
                  </p>
                )}

                {interruptValue.time && (
                  <p>
                    <span className="font-medium">Time:</span>{" "}
                    {interruptValue.time}
                  </p>
                )}
              </div>
            )}

            {isEmailQuestion ? (
              <form
                onSubmit={(event) => {
                  event.preventDefault();

                  const email = emailInput.trim();

                  if (!email || isResponding) {
                    return;
                  }

                  setEmailInput("");
                  handleApproval(email);
                }}
                className="mt-5 flex flex-wrap items-center gap-3"
              >
                <input
                  type="email"
                  value={emailInput}
                  onChange={(event) => setEmailInput(event.target.value)}
                  placeholder="you@example.com"
                  required
                  autoFocus
                  disabled={isResponding}
                  className="min-w-[220px] flex-1 rounded-full border border-black/10 bg-white px-4 py-2.5 text-sm outline-none focus:border-black/30 disabled:opacity-50"
                />

                <button
                  type="submit"
                  disabled={isResponding || !emailInput.trim()}
                  className="rounded-full bg-black px-5 py-2.5 text-sm font-medium text-white transition hover:scale-[1.02] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isResponding ? "Processing..." : "Continue"}
                </button>

                <button
                  type="button"
                  onClick={() => handleApproval(false)}
                  disabled={isResponding}
                  className="rounded-full border border-black/10 bg-white px-5 py-2.5 text-sm font-medium text-black transition hover:bg-black/5 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Cancel
                </button>
              </form>
            ) : (
              <div className="mt-5 flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={() => handleApproval(true)}
                  disabled={isResponding}
                  className="rounded-full bg-black px-5 py-2.5 text-sm font-medium text-white transition hover:scale-[1.02] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isResponding ? "Processing..." : approvalLabels.yes}
                </button>

                <button
                  type="button"
                  onClick={() => handleApproval(false)}
                  disabled={isResponding}
                  className="rounded-full border border-black/10 bg-white px-5 py-2.5 text-sm font-medium text-black transition hover:bg-black/5 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {approvalLabels.no}
                </button>
              </div>
            )}
          </div>
        )}

        <div className="w-full max-w-2xl">
          <form
            onSubmit={handleSubmit}
            className="flex items-center gap-3 rounded-2xl border border-black/10 bg-white px-4 py-3 shadow-lg"
          >
            <input
              type="text"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Start booking..."
              disabled={isLoading || isResponding || !!interruptValue}
              className="flex-1 bg-transparent text-sm outline-none placeholder:text-black/35 disabled:opacity-50"
            />

            <button
              type="submit"
              disabled={
                isLoading ||
                isResponding ||
                !!interruptValue ||
                !input.trim()
              }
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-black text-white transition hover:scale-105 disabled:cursor-not-allowed disabled:opacity-40"
              aria-label="Send message"
            >
              →
            </button>
          </form>
        </div>

        {chatMessages.length === 0 && !interruptValue && (
          <p className="mt-8 max-w-2xl text-center text-lg font-semibold tracking-wide text-black/70">
            Your AI reservation assistant to restaurants and fine cuisines.
          </p>
        )}

        {(isLoading || isResponding) && (
          <p className="mt-4 text-xs text-black/40">
            Reseva is thinking...
          </p>
        )}

        {errorMessage && (
          <p className="mt-4 max-w-2xl text-center text-sm text-red-600">
            {errorMessage}
          </p>
        )}
      </section>

      <footer className="pb-8 text-xs text-black/25">
        Powered by AI
      </footer>
    </main>
  );
}

export default App;