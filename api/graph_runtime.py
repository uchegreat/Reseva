import os

from dotenv import load_dotenv
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from agent.advanced_graph import compile_advanced_graph


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError(
        "DATABASE_URL is not set in the .env file."
    )

PSYCOPG_DATABASE_URL = DATABASE_URL.replace(
    "postgresql+psycopg://",
    "postgresql://",
)


class ResevaGraphRuntime:
    def __init__(self):
        self._context = None
        self.checkpointer = None
        self.graph = None

    async def __aenter__(self):
        self._context = AsyncPostgresSaver.from_conn_string(
            PSYCOPG_DATABASE_URL
        )

        self.checkpointer = await self._context.__aenter__()

        self.graph = compile_advanced_graph(
            self.checkpointer
        )

        return self.graph

    async def __aexit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        return await self._context.__aexit__(
            exc_type,
            exc_value,
            traceback,
        )