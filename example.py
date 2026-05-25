from webview_tkinter import WebViewWindow


def receive_from_frontend(params):
    print("Received from frontend:")
    print(params)
    web_app.expose_function.send("ping_python", {"message": "Hello from Python!"})
    return f"Received in Python: {params}"


def open_top_level(params):
    web_app.topLevel("tela1.html", title="Screen 1", window_size=(800, 600))
    return f"Top level opened with params: {params}"


web_app = WebViewWindow("index.html", window_size=(1280, 720), title="Bridge demo")
web_app.openAccessExpose(["index.html", "tela1.html"])
web_app.openAccessSite(["index.html", "tela1.html"])
web_app.expose_function.receive("ping_python", receive_from_frontend)
web_app.expose_function.receive("top_level", open_top_level)
web_app.run()
