from webview_tkinter import WebViewWindow

def receive_from_frontend(params):
    print("Received from frontend:")
    print(params)
    web_app.expose_function.send("ping_python", {"message": "Hello from Python!"})
    return f"Received in Python: {params}"

def events(event):
    print(event)
    if event["name"] == "close_requested":
        web_app.system_tray.alert(
            "view/html/alert.html",
            window_size=(420, 400),
            duration_ms=12000,
            close_buttom=True,
            padding=(24, 132),
        )

def open_top_level(params):
    web_app.top_level("view/html/tela1.html", title="Screen 1", window_size=(800, 600), events=events)
    return f"Top level opened with params: {params}"


def tray_about(window):
    print("Tray action", window.title)

def auth(params): 
    print("Middleware auth called")
    # Here you can implement your authentication logic
    # For demonstration, we'll just allow access
    web_app.redirect("view/html/index.html")

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
    ["view/html/index.html", "view/html/tela1.html", "view/html/tela2.html", "view/html/alert.html"]
)
web_app.open_access_site(
    ["view/html/index.html", "view/html/tela1.html", "view/html/tela2.html", "view/html/alert.html"]
)

web_app.middleware(
    ["view/html/tela2.html"], 
    auth
)
web_app.expose_function.receive("ping_python", receive_from_frontend)
web_app.expose_function.receive("top_level", open_top_level)
web_app.run()
