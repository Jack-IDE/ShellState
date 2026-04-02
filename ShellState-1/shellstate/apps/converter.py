"""Unit Converter screens and behavior."""

from shellstate.core.runtime_model import (
    _MAX_CONVERTER_RECENT,
    _converter_store,
    _record_activity,
)

def make_converter(pairs: list) -> tuple:
    def on_render(app):
        last = _converter_store(app).get("last_result", "")
        width_getter = getattr(app, "_terminal_width", None)
        width = width_getter() if callable(width_getter) else 80
        line = f"Last result: {last}" if last else "Select a conversion and enter a value."
        print(app._align_line(line, width, "center"))

    def make_action(from_u, to_u, factor):
        def action(app):
            raw = app.prompt_text(f"{from_u}", title="CONVERTER", allow_empty=False)
            if raw is None:
                app.set_status("Input canceled.")
                return
            try:
                value = float(raw)
            except ValueError:
                app.set_status("Enter a valid number.")
                return
            if from_u == "K" and value < 0:
                app.set_status("Kelvin cannot be negative.")
                return
            result = factor(value) if callable(factor) else value * factor
            if to_u == "K" and result < 0:
                app.set_status("Result would be below absolute zero.")
                return
            entry = f"{value:g} {from_u} = {result:.5g} {to_u}"
            converter = _converter_store(app)
            converter["last_result"] = entry
            recent = converter.setdefault("recent", [])
            recent.append(entry)
            converter["recent"] = recent[-_MAX_CONVERTER_RECENT:]
            _record_activity(app, f"Converted {from_u} to {to_u}")
            app.set_status(entry)

        return action

    options = [label for label, *_ in pairs] + ["Back"]
    actions = [make_action(f, t, k) for _, f, t, k in pairs] + ["back"]
    return on_render, options, actions


_l_render, _l_opts, _l_acts = make_converter([
    ("km → miles", "km", "miles", 0.621371),
    ("miles → km", "miles", "km", 1.60934),
    ("meters → feet", "m", "ft", 3.28084),
    ("feet → meters", "ft", "m", 0.3048),
    ("cm → inches", "cm", "in", 0.393701),
    ("inches → cm", "in", "cm", 2.54),
])

_w_render, _w_opts, _w_acts = make_converter([
    ("kg → lbs", "kg", "lbs", 2.20462),
    ("lbs → kg", "lbs", "kg", 0.453592),
    ("g → oz", "g", "oz", 0.035274),
    ("oz → g", "oz", "g", 28.3495),
    ("kg → stones", "kg", "st", 0.157473),
    ("stones → kg", "st", "kg", 6.35029),
])

_t_render, _t_opts, _t_acts = make_converter([
    ("°C → °F", "°C", "°F", lambda c: c * 9 / 5 + 32),
    ("°F → °C", "°F", "°C", lambda f: (f - 32) * 5 / 9),
    ("°C → K", "°C", "K", lambda c: c + 273.15),
    ("K → °C", "K", "°C", lambda k: k - 273.15),
    ("°F → K", "°F", "K", lambda f: (f + 459.67) * 5 / 9),
    ("K → °F", "K", "°F", lambda k: k * 9 / 5 - 459.67),
])


def register_converter_screens(app) -> None:
    app.add_screen(
        name="conv_length",
        title="Length Converter",
        options=_l_opts,
        actions=_l_acts,
        on_render=_l_render,
        hotkeys={"b": "back"},
    )

    app.add_screen(
        name="conv_weight",
        title="Weight Converter",
        options=_w_opts,
        actions=_w_acts,
        on_render=_w_render,
        hotkeys={"b": "back"},
    )

    app.add_screen(
        name="conv_temp",
        title="Temperature Converter",
        options=_t_opts,
        actions=_t_acts,
        on_render=_t_render,
        hotkeys={"b": "back"},
    )

    app.add_screen(
        name="converter",
        title="Unit Converter",
        options=["Length", "Weight", "Temperature", "Back"],
        actions=["conv_length", "conv_weight", "conv_temp", "back"],
        hotkeys={"b": "back"},
    )
