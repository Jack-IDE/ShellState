"""Calculator app screens and behavior."""

from shellstate.runtime_model import *

_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _checked_number(value: float) -> float:
    if abs(value) > _MAX_CALC_ABS_VALUE:
        raise ValueError("Number too large")
    return value


def _safe_eval(expr: str) -> float:
    expr = expr.strip()
    if len(expr) > _MAX_CALC_EXPR_LEN:
        raise ValueError("Expression too long")

    def _node(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return _checked_number(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_OPS:
            left = _node(node.left)
            right = _node(node.right)
            value = _SAFE_OPS[type(node.op)](left, right)
            return _checked_number(value)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_OPS:
            value = _SAFE_OPS[type(node.op)](_node(node.operand))
            return _checked_number(value)
        raise ValueError("Unsupported expression")

    tree = ast.parse(expr, mode="eval")
    return _node(tree.body)


def _fmt_result(value: float) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return f"{value:.6g}"


def _calculator_expr(app) -> str:
    return str(_calculator_store(app).get("expr_buffer", "") or "")


def _calculator_cursor(app) -> int:
    calculator = _calculator_store(app)
    expr = _calculator_expr(app)
    cursor = int(calculator.get("expr_cursor", len(expr)) or 0)
    return max(0, min(cursor, len(expr)))


def _calculator_set_expr(app, expr: str, cursor: int | None = None) -> None:
    calculator = _calculator_store(app)
    expr = str(expr or "")
    calculator["expr_buffer"] = expr
    if cursor is None:
        cursor = len(expr)
    calculator["expr_cursor"] = max(0, min(int(cursor), len(expr)))


def _calculator_history_entries(app) -> list[str]:
    return list(_calculator_store(app).get("history", []) or [])


def _calculator_history_expr(entry: str) -> str:
    text = str(entry or "")
    if " = " not in text:
        return text
    return text.rsplit(" = ", 1)[0]


def render_calculator_main_panel(app):
    calculator = _calculator_store(app)
    expr = _calculator_expr(app)
    cursor = _calculator_cursor(app)
    width = max(18, app._terminal_width() - 6)
    visible_expr = app._input_visible_text(expr, cursor, width)
    history = _calculator_history_entries(app)
    last_result = calculator.get("last_result")

    print("  Type directly in the expression line.")
    print("  Press Enter to calculate.")
    print("")
    print("  Expression:")
    print(f"  {visible_expr}")
    print("")
    print("  Operators: +  -  *  /  **  %  //  ()")
    if last_result not in (None, ""):
        print(f"  Last result: {last_result}")
    else:
        print("  Last result: (none yet)")
    print("")
    if history:
        print("  Recent calculations:")
        for idx, entry in enumerate(history[-8:], max(1, len(history) - min(len(history), 8) + 1)):
            print(f"    {idx:>2}. {entry}")
    else:
        print("  No calculations yet.")
        print("")
        print("  Try:")
        print("    12 * (3 + 4)")


def do_calculate(app, expr: str | None = None):
    expr = _calculator_expr(app) if expr is None else str(expr)
    if not expr.strip():
        app.set_status("Nothing entered.")
        return
    try:
        result = _safe_eval(expr)
        entry = f"{expr.strip()} = {_fmt_result(result)}"
        calculator = _calculator_store(app)
        history = calculator.setdefault("history", [])
        history.append(entry)
        limit = max(1, int(_system_settings(app).get("calc_history_limit", 30)))
        calculator["history"] = history[-limit:]
        calculator["last_result"] = _fmt_result(result)
        calculator["history_browse_index"] = -1
        _calculator_set_expr(app, expr.strip(), len(expr.strip()))
        _record_activity(app, f"Calculated '{expr.strip()}'")
        app.set_status(f"= {_fmt_result(result)}")
    except ZeroDivisionError:
        app.set_status("Error: Division by zero.")
    except ValueError as exc:
        app.set_status(f"Error: {exc}")
    except Exception as exc:
        app.set_status(f"Error: {type(exc).__name__}: {exc}")


def clear_calc_history(app):
    calculator = _calculator_store(app)
    calculator["history"] = []
    calculator["last_result"] = ""
    calculator["history_browse_index"] = -1
    _record_activity(app, "Cleared calculator history")
    app.set_status("History cleared.")


def clear_calc_expression(app):
    _calculator_set_expr(app, "", 0)
    _calculator_store(app)["history_browse_index"] = -1
    app.set_status("Expression cleared.")


def _calculator_recall_history(app, step: int) -> None:
    history = _calculator_history_entries(app)
    if not history:
        app.set_status("No calculation history.")
        return
    calculator = _calculator_store(app)
    index = int(calculator.get("history_browse_index", -1) or -1)
    if index < 0:
        index = len(history)
    index = max(0, min(index + step, len(history)))
    if index >= len(history):
        calculator["history_browse_index"] = -1
        _calculator_set_expr(app, "", 0)
        app.set_status("Live entry restored.")
        return
    calculator["history_browse_index"] = index
    expr = _calculator_history_expr(history[index])
    _calculator_set_expr(app, expr, len(expr))
    app.set_status(f"Recalled #{index + 1}.")


def handle_calculator_key(app, key: str):
    expr = _calculator_expr(app)
    cursor = _calculator_cursor(app)
    calculator = _calculator_store(app)

    if key == "ESC":
        app.go_back()
        return True
    if key == "ENTER":
        do_calculate(app)
        return True
    if key == "BACKSPACE":
        if cursor > 0:
            expr = expr[:cursor - 1] + expr[cursor:]
            cursor -= 1
            _calculator_set_expr(app, expr, cursor)
            calculator["history_browse_index"] = -1
        return True
    if key == "LEFT":
        _calculator_set_expr(app, expr, max(0, cursor - 1))
        return True
    if key == "RIGHT":
        _calculator_set_expr(app, expr, min(len(expr), cursor + 1))
        return True
    if key == "UP":
        _calculator_recall_history(app, -1)
        return True
    if key == "DOWN":
        _calculator_recall_history(app, 1)
        return True
    if key == "C":
        clear_calc_expression(app)
        return True
    if key == "X":
        clear_calc_history(app)
        return True
    if isinstance(key, str) and len(key) == 1 and key.isprintable():
        expr = expr[:cursor] + key + expr[cursor:]
        cursor += 1
        _calculator_set_expr(app, expr, cursor)
        calculator["history_browse_index"] = -1
        return True
    return True


app.add_screen(
    name="calculator",
    title="Calculator",
    options=[],
    actions=[],
    main_panel=render_calculator_main_panel,
    main_title="Calculator",
    screen_type="workspace_full",
)
app.screens["calculator"]["interaction_mode"] = "typing"
app.screens["calculator"]["hide_menu"] = True
app.screens["calculator"]["on_key"] = handle_calculator_key
app.screens["calculator"]["footer_text"] = (
    "[Typing Mode]  [Enter] Calculate  [Arrows] Move/Recall  [Shift+C] Clear Expr  [Shift+X] Clear History  [Esc] Back"
)
