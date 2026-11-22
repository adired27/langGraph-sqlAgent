"""Web front end.  Run: streamlit run app.py"""
import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from agent import DB_PATH, build_graph, connect  # noqa: E402
from data.seed import build as build_database  # noqa: E402

MAX_QUESTIONS = 10  # per visitor session, to limit API spend on the public app

EXAMPLES = [
    "Which city brings in the most revenue, and who is the top spender there?",
    "For each product category, what percentage of orders were cancelled?",
    "Which customers spent more in 2026 than in 2025?",
    "What's the average order value by month in 2026, and which month was the highest?",
]

st.set_page_config(page_title="Talk to Your Data", page_icon="💬", layout="wide")


@st.cache_resource
def get_graph():
    if not DB_PATH.exists():  # e.g. on a fresh deploy
        build_database()
    return build_graph()


def load_tables():
    """Return {table: (schema rows, data rows as dicts)} for the Browse tab."""
    db = connect()
    tables = {}
    for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        schema = [{"column": c[1], "type": c[2], "primary key": bool(c[5])}
                  for c in db.execute(f"PRAGMA table_info({name})")]
        cursor = db.execute(f"SELECT * FROM {name}")
        cols = [c[0] for c in cursor.description]
        tables[name] = (schema, [dict(zip(cols, r)) for r in cursor.fetchall()])
    return tables


def run_agent(question):
    """Stream the graph, showing each step live. Returns the final result."""
    result = {}
    with st.status("Thinking...", expanded=True) as status:
        for step in get_graph().stream({"question": question}, stream_mode="updates"):
            for node, update in step.items():
                result.update(update)
                if node == "get_schema":
                    st.write("📋 Read the database structure")
                elif node == "generate_sql":
                    st.write(f"✍️ Wrote SQL (attempt {update['attempts']})")
                    st.code(update["sql"], language="sql")
                elif node == "execute_sql" and update.get("error"):
                    st.write(f"⚠️ Query failed: `{update['error']}`. Retrying...")
                elif node == "execute_sql":
                    st.write(f"✅ Ran the query: {len(update['rows'])} row(s)")
        failed = bool(result.get("error"))
        status.update(label="Couldn't answer" if failed else "Done", state="error" if failed else "complete",
                      expanded=False)
    return result


def show_result(result):
    st.markdown(result["answer"])
    if result.get("rows"):
        with st.expander("See the SQL and data", expanded=True):
            st.code(result["sql"], language="sql")
            st.dataframe([dict(zip(result["columns"], r)) for r in result["rows"]], hide_index=True)


# --- main -----------------------------------------------------------------
st.title("💬 Talk to Your Data")
st.caption("Ask a question in plain English. The agent writes SQL, runs it, fixes its own mistakes, "
           "and explains the answer. Read-only: it can never change data.")

if not os.getenv("ANTHROPIC_API_KEY", "").startswith("sk-ant-"):
    st.error("The Anthropic API key is missing or malformed. Add ANTHROPIC_API_KEY to `.env` "
             "(local) or to the app's Secrets (Streamlit Cloud), then restart.")
    st.stop()

get_graph()  # builds the database first if it's missing

ask_tab, data_tab = st.tabs(["💬 Ask", "🗂️ Browse data"])

with ask_tab:
    st.session_state.setdefault("chat", [])
    limit_reached = len(st.session_state.chat) // 2 >= MAX_QUESTIONS

    # Example prompts, always visible at the top
    st.caption("Try an example:")
    cols = st.columns(2)
    for i, example in enumerate(EXAMPLES):
        if cols[i % 2].button(example, key=f"ex{i}", use_container_width=True, disabled=limit_reached):
            st.session_state.pending = example
            st.rerun()

    if limit_reached:
        st.info(f"You've reached the demo limit of {MAX_QUESTIONS} questions. Thanks for trying it out!")
    question = st.chat_input("Or ask your own question...", disabled=limit_reached) \
        or st.session_state.pop("pending", None)

    for msg in st.session_state.chat:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant":
                show_result(msg["result"])
            else:
                st.markdown(msg["text"])

    if question:
        st.session_state.chat.append({"role": "user", "text": question})
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            result = run_agent(question)
            show_result(result)
        st.session_state.chat.append({"role": "assistant", "result": result})

    if st.session_state.chat and st.button("🗑️ Clear chat"):
        st.session_state.chat = []
        st.rerun()

with data_tab:
    tables = load_tables()
    for tab, (name, (schema, rows)) in zip(st.tabs(list(tables)), tables.items()):
        with tab:
            schema_col, data_col = st.columns([1, 3])
            with schema_col:
                st.subheader("Schema")
                st.dataframe(schema, hide_index=True)
            with data_col:
                st.subheader(f"Data ({len(rows)} rows)")
                st.dataframe(rows, hide_index=True, height=420)
