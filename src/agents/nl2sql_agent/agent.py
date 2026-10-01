"""A NL2SQL agent that repairs its own queries from database errors.

Topic 4: "the agent uses database error messages as feedback to correct and
regenerate SQL queries". The loop is assembled from pieces that already
exist rather than hand-rolled:

  - `run_sql_query` raises with the database's own wording attached.
  - ADK's `ReflectAndRetryToolPlugin` catches that, counts the failure for
    this tool within the invocation, and hands the model structured guidance
    asking it not to repeat the same call.
  - The model rewrites the query and calls the tool again.
  - A success resets the counter; exceeding `max_retries` stops the loop.

Writing the retry loop by hand would mean reimplementing per-tool failure
tracking, concurrency-safe counters and scope handling that the plugin
already provides.
"""

from __future__ import annotations

from google.adk.agents.llm_agent import LlmAgent
from google.adk.apps.app import App
from google.adk.plugins.reflect_retry_tool_plugin import ReflectAndRetryToolPlugin

from src.agents.nl2sql_agent.tools import describe_schema, run_sql_query
from src.utils.accounting import TokenAccountantPlugin
from src.utils.model import get_geofenced_gemini_model
from src.utils.patch import apply_adk_patch
from src.utils.thinking import planner_from_env

apply_adk_patch()

#: Three attempts is enough for the common repairs (a misspelled column, a
#: wrong function, a dialect slip) without letting a hopeless query burn a
#: whole eval budget.
MAX_SQL_RETRIES = 3

INSTRUCTION = """\
You answer questions about a retail banking database by writing and running \
SQL.

Procedure:
1. If you are unsure of a table or column name, call `describe_schema` first. \
Guessing a name is the most common cause of a failed query.
2. Write one read-only SELECT (or WITH ... SELECT) statement and run it with \
`run_sql_query`.
3. Answer the user's question in plain language, citing the numbers you got \
back. Do not invent values that are not in the result.

When a query fails you are given the database's own error message, the SQL \
you sent and the schema. Read the error before retrying:
- "no such column" or "no such table" means the name is wrong. Check the \
schema and use the exact name.
- A syntax error usually means a function that this database does not have. \
Prefer plain, standard SQL.
Never resend a query that has already failed unchanged.

If a query still fails after several attempts, say what you tried and why it \
did not work. Do not fabricate an answer.
"""

root_agent = LlmAgent(
    name="nl2sql_agent",
    instruction=INSTRUCTION,
    model=get_geofenced_gemini_model(),
    tools=[describe_schema, run_sql_query],
    planner=planner_from_env(),
)

app = App(
    name="nl2sql_agent",
    root_agent=root_agent,
    plugins=[
        # Order matters only for readability; the two are independent.
        ReflectAndRetryToolPlugin(max_retries=MAX_SQL_RETRIES),
        TokenAccountantPlugin(),
    ],
)
