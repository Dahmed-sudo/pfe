import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER

def build(app):
    # Main container
    main_box = toga.Box(style=Pack(direction=COLUMN, padding=10))

    # Dashboard title
    title = toga.Label(
        "DASHBOARD",
        style=Pack(font_size=20, font_weight="bold", padding_bottom=10, text_align=CENTER)
    )
    main_box.add(title)

    # Grid layout for metrics
    grid = toga.Box(style=Pack(direction=ROW, wrap=True, padding=5))

    # Metric cards (without icons)
    metrics = [
        {"label": "Temperature (°C)", "value": "25.5", "color": "red"},
        {"label": "Humidity (%)", "value": "95", "color": "blue"},
        {"label": "Gas Level (ppm)", "value": "30", "color": "gray"},
        {"label": "Flame", "value": "40", "color": "orange"},
        {"label": "Vibration", "value": "False", "color": "purple"},
        {"label": "consommation d'énergie (kWh)", "value": "100", "color": "green"},
        {"label": "défautes", "value": "3", "color": "red"},
        {"label": "nom défautes", "value": "30", "color": "blue"},
    ]

    for metric in metrics:
        card = toga.Box(style=Pack(
            direction=COLUMN,
            padding=10,
            background_color="#f0f0f0",
            border_radius=8,
            width=150,
            height=150,
            alignment=CENTER
        ))
        card.add(toga.Label(
            metric["label"],
            style=Pack(font_size=12, color="#666", text_align=CENTER, padding=5)
        ))
        card.add(toga.Label(
            metric["value"],
            style=Pack(font_size=18, font_weight="bold", color=metric["color"], text_align=CENTER)
        ))
        grid.add(card)

    main_box.add(grid)

    # Bottom navigation
    nav_box = toga.Box(style=Pack(direction=ROW, justify="space-around", padding=10))
    nav_box.add(toga.Button("Settings", on_press=lambda w: print("Settings")))
    nav_box.add(toga.Button("Profile", on_press=lambda w: print("Profile")))
    nav_box.add(toga.Button("Logout", on_press=lambda w: print("Logout")))
    main_box.add(nav_box)

    return main_box

def main():
    return toga.App("Industrial Dashboard", "org.example.dashboard", startup=build)

if __name__ == "__main__":
    main().main_loop()