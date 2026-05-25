from webview_tkinter import WebViewWindow

def receive_from_frontend(params):
    print("Received from frontend:")
    print(params)
    web_app.expose_function.send("ping_python", {"message": "Hello from Python!"})
    return f"Received in Python: {params}"

def events(event):
    print(event)

def open_top_level(params):
    web_app.top_level("view/html/tela1.html", title="Screen 1", window_size=(800, 600), events=events)
    return f"Top level opened with params: {params}"


def tray_about(window):
    print("Tray action", window.title)

web_app = WebViewWindow("view/html/index.html", window_size=(1280, 720), title="Bridge demo", events=events)
web_app.debug_mode(True)

web_app.system_tray(
    True,
    tooltip="Bridge demo",
    close_to_tray=True,
    menu_items=[
        {"label": "About", "callback": tray_about},
    ],
)

web_app.open_access_expose(
    ["view/html/index.html", "view/html/tela1.html", "view/html/tela2.html"]
)
web_app.open_access_site(
    ["view/html/index.html", "view/html/tela1.html", "view/html/tela2.html"]
)
web_app.expose_function.receive("ping_python", receive_from_frontend)
web_app.expose_function.receive("top_level", open_top_level)
web_app.run()
