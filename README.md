# WebView Tkinter

Created by Carlos Jaime de Andrade Junior

A Python library for opening a Tkinter window with a modern embedded web page.

This version uses `tkwebview`, which renders through WebView2 on Windows. That gives much better HTML, CSS, and JavaScript compatibility than `tkinterweb`.

## Installation

```bash
pip install -r requirements.txt
```

## Quick Start

```python
from webview_tkinter import WebViewWindow

web_app = WebViewWindow(
    "https://example.com",
    window_size=(1280, 720),
    title="My browser",
)
web_app.run()
```

## Basic Install And Usage

1. Install the dependency:

```bash
pip install -r requirements.txt
```

2. Create your window:

```python
from webview_tkinter import WebViewWindow

web_app = WebViewWindow("index.html", window_size=(1280, 720), title="Bridge demo")
web_app.run()
```

3. Expose a Python function to JavaScript:

```python
from webview_tkinter import WebViewWindow

def receive_from_frontend(params):
    print(params)
    return f"Received in Python: {params}"

web_app = WebViewWindow("index.html", window_size=(1280, 720), title="Bridge demo")
web_app.expose_function.receive("ping_python", receive_from_frontend)
web_app.run()
```

4. Call it from HTML:

```html
<script>
  const result = await window.send.ping_python("hello", 123, { ok: true });
  console.log(result);
</script>
```

## Function Usage

```python
from webview_tkinter import open_webview

open_webview("https://example.com", window_size=(1024, 768))
```

## Parameters

- `site`: URL with `http://` or `https://`, or a path to an existing local file.
- `window_size`: optional `(width, height)` tuple. Default: `(1200, 800)`.
- `title`: optional window title.
- `min_size`: minimum window size.
- `max_size`: maximum window size.
- `position`: initial `(x, y)` position.
- `center`: centers the window on screen.
- `resizable`: `True`, `False`, or `(width, height)`.
- `fullscreen`: opens in fullscreen mode.
- `topmost`: keeps the window above others.
- `transparent_color`: transparent window color on Windows.
- `alpha`: window transparency from `0.0` to `1.0`.
- `background`: Tkinter window background color.
- `icon_path`: path to a `.ico` file or any image supported by Tkinter.
- `overrideredirect`: removes the window frame and title bar.
- `window_options`: extra options passed to `root.configure(...)`.
- `attributes`: extra options passed to `root.attributes(...)`.

## Class Methods

- `run()`: opens the window and starts the Tkinter loop.
- `navigate(site)`: navigates to another page.
- `openAccessExpose(list)`: limits which files/URLs can call the JS -> Python bridge.
- `openAccessSite(list)`: limits which files/URLs can be opened in the embedded browser.
- `lock(list)`: legacy alias for `openAccessExpose(list)`.
- `expose_function.receive(name, callback)`: registers a Python callback that can be called from the frontend.
- `expose_function.send(name, *args)`: sends data from Python to frontend callbacks.
- `expose_function(name, callback)`: shortcut for `expose_function.receive(...)`.
- `expose_object(name, instance, methods=None)`: exposes methods from a class or object.
- `reload()`: reloads the page.
- `go_back()`: navigates back.
- `go_forward()`: navigates forward.
- `evaluate_js(script)`: executes JavaScript inside the page.
- `unsafe_evaluate_js(script)`: executes JavaScript without the extra `receive` safety guard.
- `close()`: closes the window.
- `set_title(title)`: changes the window title.
- `set_window_size(width, height)`: changes the window size.
- `set_position(x, y)`: moves the window.
- `set_fullscreen(enabled)`: enables/disables fullscreen.
- `set_topmost(enabled)`: enables/disables topmost mode.
- `topLevel(site=None, window_size=None, title=None, **kwargs)`: opens a child `Toplevel` web window.

## Full Window Example

```python
app = WebViewWindow(
    "index.html",
    window_size=(1280, 720),
    title="My app",
    icon_path="app.ico",
    min_size=(900, 600),
    max_size=(1600, 1000),
    center=True,
    resizable=(True, True),
    alpha=0.98,
    background="#101418",
    attributes={"-topmost": False},
)
```

## Toplevel Window Example

You can open a child `Toplevel` window with the same configuration style:

```python
from webview_tkinter import WebViewWindow

def receive_from_frontend(params):
    if params and params[0] == "open-screen":
        web_app.topLevel(
            "tela1.html",
            window_size=(900, 600),
            title="Child window",
        )
    return "ok"

web_app = WebViewWindow("index.html", window_size=(1280, 720), title="Main window")
web_app.expose_function.receive("ping_python", receive_from_frontend)
web_app.run()
```

## Send/Receive Bridge

Python:

```python
from webview_tkinter import WebViewWindow

def present(params):
    print(params)
    web_app.expose_function.send("ping_python", "reply", params)
    return f"Received in Python: {params}"

web_app = WebViewWindow("index.html")
web_app.openAccessExpose(["index.html", "screen1.html"])
web_app.openAccessSite(["index.html", "screen1.html"])
web_app.expose_function.receive("ping_python", present)
web_app.run()
```

HTML:

```html
<script>
  window.receive.ping_python((params) => {
    console.log("from python", params);
  });

  const result = await window.send.ping_python("test", 123, { ok: true });
</script>
```

## Calling Python From HTML

Python:

```python
def present(params):
    print(params)
    return f"Received: {params}"

web_app.expose_function.receive("ping_python", present)
```

HTML:

```html
<script>
  const result = await window.send.ping_python("test", 123, { ok: true });
</script>
```

On local pages such as `index.html`, `screen1.html`, and `screen2.html`, JavaScript calls `window.send.functionName(...)`. Python registers that bridge with `web_app.expose_function.receive(...)`.

## Access Control

You can limit which pages are allowed to use the bridge:

```python
web_app.openAccessExpose([
    "index.html",
    "screen1.html",
    "https://mysite.com/dashboard",
])
```

If a page outside that list tries to call `window.send.*`, the bridge is blocked in Python.

You can also limit which pages/sites may be opened:

```python
web_app.openAccessSite([
    "index.html",
    "screen1.html",
    "https://mysite.com/dashboard",
])
```

If navigation tries to open anything outside that list, the library blocks it and returns to the home page defined in `WebViewWindow("index.html", ...)`.

## Extra Safety In `receive`

By default, while a callback registered with `expose_function.receive(...)` is running, the library blocks `evaluate_js()`. This helps prevent frontend-provided data from being reused unsafely as raw JavaScript.

Use the safer channel:

```python
web_app.expose_function.send("ping_python", {"message": "ok"})
```

If you really need raw JS execution in that flow, use:

```python
web_app.unsafe_evaluate_js("console.log('debug')")
```

If a callback only accepts one parameter, the library passes all frontend values as a single tuple:

```python
def my_function(params):
    print(params)
    return "ok"

web_app.expose_function("my_function", my_function)
```

In that case, `params` receives a tuple with everything sent from JavaScript.

If you prefer, you can still use `*args`:

```python
def my_function(*args):
    print(args)
    return "ok"
```

Callbacks with no parameters also work:

```python
def test():
    print("Exposed function called")

web_app.expose_function("ping_python", lambda: test())
```

In that case, extra frontend arguments are ignored.

Exposing object methods:

```python
class DesktopActions:
    def set_title(self, title):
        web_app.root.title(title)
        return "ok"

web_app.expose_object("desktop", DesktopActions(), methods=["set_title"])
```

HTML:

```html
<script>
  await window.desktop.set_title("New title");
</script>
```

## Notes

- This library is focused on Windows.
- It requires Microsoft Edge WebView2 Runtime to be installed.
- Local `.html` files are supported as long as the path exists.
