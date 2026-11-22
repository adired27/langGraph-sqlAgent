"""
python main.py "Which city has the most customers?"   # one question
python main.py                                        # keep asking questions
python main.py --graph                                # print the graph as Mermaid
"""
import sys

from dotenv import load_dotenv

load_dotenv()  # reads ANTHROPIC_API_KEY from .env

from agent import DB_PATH, build_graph  # noqa: E402


def ask(graph, question):
    # stream() shows each step as it happens
    for step in graph.stream({"question": question}, stream_mode="updates"):
        for node, update in step.items():
            if node == "generate_sql":
                print(f"  [sql #{update['attempts']}] {update['sql']}")
            elif node == "execute_sql" and update.get("error"):
                print(f"  [error] {update['error']}")
            elif node == "answer":
                print(f"\n{update['answer']}")


def main():
    if not DB_PATH.exists():
        sys.exit("No database yet. Run: python data/seed.py")

    graph = build_graph()

    if "--graph" in sys.argv:
        print(graph.get_graph().draw_mermaid())
    elif len(sys.argv) > 1:
        ask(graph, " ".join(sys.argv[1:]))
    else:
        print("Ask a question about the store (or 'q' to quit).")
        while (q := input("\n> ").strip()) not in ("q", "quit", "exit"):
            if q:
                ask(graph, q)


if __name__ == "__main__":
    main()
