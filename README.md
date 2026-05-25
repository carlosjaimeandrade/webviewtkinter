# WebView Tkinter

Created by Carlos Jaime de Andrade Junior

A Python library for opening a Tkinter window with a modern embedded web page.

This version uses `tkwebview`, which renders through WebView2 on Windows. That gives much better HTML, CSS, and JavaScript compatibility than `tkinterweb`.

## Installation

```bash
pip install -r requirements.txt
```

## Frontend Bundle

When your frontend is inside `view/html`, `view/css`, and `view/js`, run:

```bash
py deploy_content.py
```

This command reads every HTML file in `view/html`, loads the CSS and JS referenced by that HTML, and generates a file called `frontend.py`.

Why this exists:

- It embeds your frontend into Python so the app can open pages without depending on loose `.html`, `.css`, and `.js` files at runtime.
- It makes packaging and deployment easier, because `WebViewWindow("view/html/index.html", ...)` can load the page from the generated assets.
- It keeps the API the same on the Python side, while the library injects the bundled HTML/CSS/JS internally.

Important:

- Run `py deploy_content.py` every time you change files in `view/html`, `view/css`, or `view/js`.
- If `frontend.py` exists, `WebViewWindow` will prefer the bundled assets.
- If `frontend.py` does not exist, the library falls back to loading the physical files from disk.

## Quick Start

```python
from webview_tkinter import WebViewWindow

web_app = WebViewWindow(
    "https://example.com",
    window_size=(1280, 720),
    title="My browser",
    events=lambda event: print(event),
)
web_app.debug_mode(True)
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

web_app = WebViewWindow("view/html/index.html", window_size=(1280, 720), title="Bridge demo")
web_app.run()
```

3. Expose a Python function to JavaScript:

```python
from webview_tkinter import WebViewWindow

def receive_from_frontend(params):
    print(params)
    return f"Received in Python: {params}"

web_app = WebViewWindow("view/html/index.html", window_size=(1280, 720), title="Bridge demo")
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
- `site`: URL with `http://` or `https://`, a local file path, or a bundled page path such as `view/html/index.html` when `frontend.py` has been generated.
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
- `events`: optional callback that receives Tkinter window lifecycle and state events for that specific window.

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
- `debug_mode(enabled=True)`: enables or disables browser debug behavior.
- `system_tray(enabled=True, **kwargs)`: enables system tray support for the window.
- `system_tray.alert(site, **kwargs)`: opens a tray-style popup window using a normal `WebViewWindow` with bridge support.
- `close()`: closes the window.
- `set_title(title)`: changes the window title.
- `set_window_size(width, height)`: changes the window size.
- `set_position(x, y)`: moves the window.
- `set_fullscreen(enabled)`: enables/disables fullscreen.
- `set_topmost(enabled)`: enables/disables topmost mode.
- `open_access_expose(list)`: `snake_case` version of `openAccessExpose(...)`.
- `open_access_site(list)`: `snake_case` version of `openAccessSite(...)`.
- `top_level(site=None, window_size=None, title=None, **kwargs)`: `snake_case` version of `topLevel(...)`.
- `debugMode(enabled=True)`: `camelCase` alias for `debug_mode(...)`.
- `SystemTray(enabled=True, **kwargs)`: `camelCase` alias for `system_tray(...)`.
- `topLevel(site=None, window_size=None, title=None, **kwargs)`: opens a child `Toplevel` web window.

## System Tray

You can enable system tray support like this:

```python
web_app = WebViewWindow(
    "view/html/index.html",
    window_size=(1280, 720),
    title="Bridge demo",
)

web_app.system_tray(
    True,
    tooltip="Bridge demo",
    close_to_tray=True,
)

web_app.run()
```

What it does:

- Creates a tray icon for the window.
- Adds default tray actions such as `Restore` and `Quit`.
- If `close_to_tray=True`, clicking the window close button hides the window and sends it to the tray instead of exiting the app.

Main parameters:

- `enabled`: enables or disables tray support.
- `icon_path`: optional icon file for the tray icon.
- `tooltip`: text shown in the tray icon tooltip.
- `close_to_tray`: if `True`, clicking the close button sends the window to the tray instead of closing it.
- `allow_restore`: shows the `Restore` action in the tray menu.
- `allow_quit`: shows the `Quit` action in the tray menu.
- `menu_items`: optional custom tray menu items.

About `close_to_tray`:

- If `close_to_tray=True`, clicking the window `X` does not destroy the app window.
- Instead, the window is hidden with `withdraw()` and stays alive in the system tray.
- You can then restore it from the tray menu.
- If `close_to_tray=False`, clicking the `X` closes the window normally.

Example with a custom menu item:

```python
def about(window):
    print("Tray action from:", window.title)

web_app.system_tray(
    True,
    tooltip="Bridge demo",
    close_to_tray=True,
    menu_items=[
        {"label": "About", "callback": about},
    ],
)
```

You can also use:

```python
web_app.SystemTray(True, tooltip="Bridge demo", close_to_tray=True)
```

### Tray Alerts

You can open a popup near the system clock with:

```python
web_app.system_tray.alert(
    "view/html/alert.html",
    window_size=(420, 240),
)
```

This alert is not a fake HTML layer. It is a real child `WebViewWindow`, so it supports:

- `window.send.*`
- `window.receive.*`
- `web_app.expose_function.receive(...)`
- `web_app.expose_function.send(...)`
- bundled pages from `frontend.py`

Example:

```python
def events(event):
    print(event)
    if event["name"] == "close_requested":
        web_app.system_tray.alert(
            "view/html/alert.html",
            window_size=(420, 240),
            duration_ms=12000,
            close_buttom=True,
            padding=(24, 72),
        )
```

Main alert parameters:

- `site`: page to open in the alert popup, such as `view/html/alert.html`.
- `window_size`: popup size.
- `title`: optional popup title.
- `duration_ms`: auto-close time in milliseconds. If omitted, the popup stays open until closed.
- `padding`: controls the distance from the bottom-right corner of the screen.
- `close_buttom`: if `True`, shows a visual close button inside the popup.
- `close_button`: alternative spelling for the same behavior.
- `events`: optional callback specific to the alert window.

About `padding`:

- `padding=(x, y)`
- `x` controls how far the alert stays from the right edge.
- `y` controls how far the alert stays from the bottom edge.
- Higher `x` moves it more to the left.
- Higher `y` moves it more upward.

Example:

```python
web_app.system_tray.alert(
    "view/html/alert.html",
    window_size=(420, 240),
    padding=(40, 120),
)
```

This makes the popup appear farther from the taskbar and more to the left.

About `close_buttom`:

- This parameter keeps the current API exactly as implemented in the project.
- If `close_buttom=True`, a `×` button is injected inside the popup.
- Clicking that button closes only the alert window.
- The close button also sends the normal bridge metadata, so access rules still work correctly.

## Window Events

You can listen to window events with the `events` callback:

```python
from webview_tkinter import WebViewWindow

def events(event):
    print(event)

web_app = WebViewWindow(
    "view/html/index.html",
    window_size=(1280, 720),
    title="Bridge demo",
    events=events,
)
web_app.run()
```

You can also pass `events=...` to a child window:

```python
def events(event):
    print(event)

def open_top_level(params):
    web_app.top_level(
        "view/html/tela1.html",
        title="Screen 1",
        window_size=(800, 600),
        events=events,
    )
    return f"Top level opened with params: {params}"
```

Each callback receives a dictionary like:

```python
{
    "name": "minimized",
    "title": "Bridge demo",
    "site": "asset://view/html/index.html",
    "asset": "view/html/index.html",
    "state": "iconic",
    "position": {"x": 120, "y": 80},
    "size": {"width": 1280, "height": 720},
    "is_top_level": False
}
```

Available event names:

- `created`
- `close_requested`
- `closing`
- `closed`
- `focus_in`
- `focus_out`
- `state_changed`
- `minimized`
- `maximized`
- `restored`
- `hidden`
- `moved`
- `resized`
- `tray_entered`
- `tray_restored`

### What Each Event Means

- `created`: the window has been created and its Tk/WebView structure is ready.
- `close_requested`: the user asked to close the window, usually by clicking the `X`.
- `closing`: the window is in the process of shutting down.
- `closed`: the window has already been destroyed.
- `focus_in`: the window gained focus.
- `focus_out`: the window lost focus.
- `state_changed`: the Tk window state changed. This is the generic state transition event.
- `minimized`: the window entered the minimized/iconic state.
- `maximized`: the window entered the maximized/zoomed state.
- `restored`: the window returned to normal after being minimized or maximized.
- `hidden`: the window became hidden or withdrawn.
- `moved`: the window position changed on screen.
- `resized`: the window size changed.
- `tray_entered`: the window was moved to the system tray.
- `tray_restored`: the window was restored from the system tray.

### Notes About Event Flow

- `close_requested` happens before `closing`.
- If `system_tray(..., close_to_tray=True)` is active, `close_requested` may be followed by `tray_entered` instead of `closing`.
- `state_changed` is the generic event, while `minimized`, `maximized`, and `restored` are the more specific interpretations of that state transition.
- `moved` and `resized` can fire many times while the user is dragging or resizing the window.
- `focus_in` and `focus_out` are useful for knowing which window is currently active.

### Example Event Handler

```python
def events(event):
    print("event:", event["name"])

    if event["name"] == "close_requested":
        web_app.system_tray.alert(
            "view/html/alert.html",
            window_size=(420, 240),
            duration_ms=12000,
            close_buttom=True,
            padding=(24, 72),
        )

    if event["name"] == "tray_restored":
        print("The main window came back from the tray.")
```

## Debug Mode

You can enable a debug-friendly browser mode with:

```python
web_app = WebViewWindow("view/html/index.html", window_size=(1280, 720), title="Bridge demo")
web_app.debug_mode(True)
web_app.run()
```

What `debug_mode(True)` does:

- Creates the WebView with browser debug support enabled.
- Makes it possible to inspect the page and access browser developer features.

What `debug_mode(False)` does:

- Blocks the context menu.
- Blocks common shortcuts such as `F12`, `Ctrl+Shift+I`, `Ctrl+Shift+J`, `Ctrl+Shift+C`, `Ctrl+U`, `Ctrl+S`, and `Ctrl+P`.
- Blocks text selection and drag start to make browser access harder.

Important:

- If you want real browser debug/devtools access, call `debug_mode(True)` before `run()`.
- After the WebView has already been created, the restricted behavior can still be applied, but debug/devtools availability depends on how the browser was created.

## Full Window Example

```python
app = WebViewWindow(
    "view/html/index.html",
    window_size=(1280, 720),
    title="My app",
    events=lambda event: print(event["name"]),
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
            "view/html/tela1.html",
            window_size=(900, 600),
            title="Child window",
            events=lambda event: print(event),
        )
    return "ok"

web_app = WebViewWindow("view/html/index.html", window_size=(1280, 720), title="Main window")
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

web_app = WebViewWindow("view/html/index.html")
web_app.openAccessExpose(["view/html/index.html", "view/html/tela1.html"])
web_app.openAccessSite(["view/html/index.html", "view/html/tela1.html"])
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

On local pages such as `view/html/index.html`, `view/html/tela1.html`, and `view/html/tela2.html`, JavaScript calls `window.send.functionName(...)`. Python registers that bridge with `web_app.expose_function.receive(...)`.

## Access Control

You can limit which pages are allowed to use the bridge:

```python
web_app.openAccessExpose([
    "view/html/index.html",
    "view/html/tela1.html",
    "https://mysite.com/dashboard",
])
```

If a page outside that list tries to call `window.send.*`, the bridge is blocked in Python.

You can also limit which pages/sites may be opened:

```python
web_app.openAccessSite([
    "view/html/index.html",
    "view/html/tela1.html",
    "https://mysite.com/dashboard",
])
```

If navigation tries to open anything outside that list, the library blocks it and returns to the home page defined in `WebViewWindow("view/html/index.html", ...)`.

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
- For bundled frontend deploys, generate `frontend.py` with `py deploy_content.py` after changing frontend files.
- System tray support uses `pystray` and `Pillow`, which are already listed in `requirements.txt`.
