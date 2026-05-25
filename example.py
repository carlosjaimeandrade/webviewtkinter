from webview_tkinter import WebViewWindow


def receive_from_frontend(params):
    print("Received from frontend:")
    print(params)
    web_app.expose_function.send("ping_python", {"message": "Hello from Python!"})
    return f"Received in Python: {params}"


web_app = WebViewWindow("index.html", window_size=(1280, 720), title="Bridge demo")
web_app.openAccessExpose(["index.html", "tela1.html"])
web_app.openAccessSite(["index.html", "tela1.html"])
web_app.expose_function.receive("ping_python", receive_from_frontend)
web_app.run()
