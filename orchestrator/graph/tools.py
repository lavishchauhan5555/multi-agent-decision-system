import os
from dotenv import load_dotenv
from langchain_community.tools import DuckDuckGoSearchRun, DuckDuckGoSearchResults
from langchain.tools import tool
import math

load_dotenv()

@tool
def calculator(expression: str) -> str:
    """
    Evaluate a mathematical expression and return the result.
    Supports: +, -, *, /, **, //, %, parentheses, and math functions
    like sqrt, sin, cos, tan, log, abs, round, pow.
    Note: use ** for exponentiation, not ^.
    Example inputs: '2 + 2', 'sqrt(144)', '(3 ** 2) * 4 / 2'
    """
    import math, re

    allowed_names = {k: v for k, v in math.__dict__.items() if not k.startswith("_")}
    allowed_names.update({"abs": abs, "round": round, "pow": pow, "min": min, "max": max})

    try:
        expression = expression.strip().strip("`").strip()

        # Replace ^ with ** so LLM-generated expressions work correctly
        expression = expression.replace("^", "**")

        result = eval(expression, {"__builtins__": {}}, allowed_names)
        return str(result)
    except ZeroDivisionError:
        return "[Calculator Error] Division by zero"
    except Exception as e:
        return f"[Calculator Error] {str(e)}"


async def get_mcp_tools():
    ddg_search  = DuckDuckGoSearchRun()
    ddg_results = DuckDuckGoSearchResults()
    from langchain_experimental.tools import PythonREPLTool
    tools = [ddg_search, ddg_results, calculator, PythonREPLTool()]
    return None, tools