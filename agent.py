import os
import re
import sqlite3
from pathlib import Path
from typing import TypedDict

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

DB_PATH = Path(__file__).parent / "data" / "shop.db"
MODEL = os.getenv("MODEL", "anthropic:claude-haiku-5-5")
MAX_ATTEMPTS = 3

# Clean a pasted key: drop spaces, line breaks, quotes and invisible characters
# (any of these break the HTTP header).
if key := os.getenv("ANTHROPIC_API_KEY"):
    os.environ["ANTHROPIC_API_KEY"] = "".join(c for c in key if c.isascii() and c.isprintable()
                                              and not c.isspace() and c not in "\"'")

SQL_PROMPT = """You write SQLite queries for the schema below.
Write exactly one read-only SELECT query. Use only tables and columns in the schema.
Sort results in a meaningful order (e.g. highest first) with ORDER BY.
Reply with ONLY the SQL, no markdown, no explanation."""

ANSWER_PROMPT = """Answer the user's question in 1-3 plain sentences using only the result rows.
Give only the final answer: no thinking out loud, no self-corrections.
If there are no rows, say no matching data was found."""


class State(TypedDict, total=False):
    question: str
    schema: str
    sql: str
    error: str | None
    attempts: int
    columns: list
    rows: list
    answer: str


def connect(path=DB_PATH):
    # Read-only: the database itself refuses any write.
    return sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro", uri=True, check_same_thread=False)


def read_schema(db):
    # Table definitions plus 2 example rows each, so the model sees real value formats.
    parts = []
    for name, ddl in db.execute("SELECT name, sql FROM sqlite_master WHERE type='table'"):
        rows = db.execute(f"SELECT * FROM {name} LIMIT 2").fetchall()
        parts.append(f"{ddl}\n-- example rows: {rows}")
    return "\n\n".join(parts)


def clean_sql(text):
    # Strip ```sql fences if the model adds them anyway.
    match = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL)
    return (match.group(1) if match else text).strip().rstrip(";")


def build_graph(llm=None, db_path=DB_PATH):
    llm = llm or init_chat_model(MODEL, max_tokens=1024)  # caps cost per call
    db = connect(db_path)

    def get_schema(state: State):
        return {"schema": read_schema(db), "attempts": 0, "error": None}

    def generate_sql(state: State):
        prompt = f"Schema:\n{state['schema']}\n\nQuestion: {state['question']}"
        if state.get("error"):
            prompt += f"\n\nYour last query:\n{state['sql']}\nfailed with: {state['error']}\nFix it."
        reply = llm.invoke([SystemMessage(SQL_PROMPT), HumanMessage(prompt)])
        return {"sql": clean_sql(reply.text), "attempts": state["attempts"] + 1}

    def execute_sql(state: State):
        sql = state["sql"]
        if not sql.lower().startswith(("select", "with")) or ";" in sql:
            return {"error": "Only a single SELECT query is allowed."}
        try:
            cursor = db.execute(sql)
            columns = [c[0] for c in cursor.description]
            return {"columns": columns, "rows": cursor.fetchmany(50), "error": None}
        except sqlite3.Error as e:
            return {"error": str(e)}

    def answer(state: State):
        if state.get("error"):
            return {"answer": f"Sorry, I couldn't answer that. Last error: {state['error']}"}
        prompt = f"Question: {state['question']}\nSQL: {state['sql']}\nRows: {state['rows']}"
        reply = llm.invoke([SystemMessage(ANSWER_PROMPT), HumanMessage(prompt)])
        return {"answer": reply.text}

    def route(state: State):
        if state["error"] and state["attempts"] < MAX_ATTEMPTS:
            return "generate_sql"
        return "answer"

    graph = StateGraph(State)
    graph.add_node("get_schema", get_schema)
    graph.add_node("generate_sql", generate_sql)
    graph.add_node("execute_sql", execute_sql)
    graph.add_node("answer", answer)

    graph.add_edge(START, "get_schema")
    graph.add_edge("get_schema", "generate_sql")
    graph.add_edge("generate_sql", "execute_sql")
    graph.add_conditional_edges("execute_sql", route, ["generate_sql", "answer"])
    graph.add_edge("answer", END)
    return graph.compile()
