from __future__ import annotations

import inspect
import json
import threading
import tkinter as tk
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urlparse

from tkwebview import TkWebview


class AppProxy:
    def __init__(self) -> None:
        self._current_app: WebViewWindow | None = None

    def _bind(self, current_app: "WebViewWindow") -> None:
        self._current_app = current_app

    def __getattr__(self, item: str):
        if self._current_app is None:
            raise RuntimeError("No WebViewWindow instance has been created yet.")
        return getattr(self._current_app, item)


app = AppProxy()


class FunctionBridge:
    def __init__(self, window: "WebViewWindow") -> None:
        self.window = window

    def __call__(
        self,
        name: str,
        callback,
        *,
        run_on_ui_thread: bool = True,
        allow_unsafe_js: bool = False,
    ) -> None:
        self.receive(
            name,
            callback,
            run_on_ui_thread=run_on_ui_thread,
            allow_unsafe_js=allow_unsafe_js,
        )

    def receive(
        self,
        name: str,
        callback,
        *,
        run_on_ui_thread: bool = True,
        allow_unsafe_js: bool = True,
    ) -> None:
        self.window._register_receive_function(
            name,
            callback,
            run_on_ui_thread=run_on_ui_thread,
            allow_unsafe_js=allow_unsafe_js,
        )

    def send(self, name: str, *args) -> None:
        self.window._emit_to_frontend(name, *args)


class WebViewWindow:
    def __init__(
        self,
        site: str,
        window_size: tuple[int, int] | list[int] | None = None,
        title: str | None = None,
        *,
        min_size: tuple[int, int] | list[int] | None = (400, 300),
        max_size: tuple[int, int] | list[int] | None = None,
        position: tuple[int, int] | list[int] | None = None,
        center: bool = False,
        resizable: tuple[bool, bool] | list[bool] | bool = (True, True),
        fullscreen: bool = False,
        topmost: bool = False,
        transparent_color: str | None = None,
        alpha: float | None = None,
        background: str | None = None,
        icon_path: str | None = None,
        overrideredirect: bool = False,
        window_options: dict[str, object] | None = None,
        attributes: dict[str, object] | None = None,
        _parent_root: tk.Tk | tk.Toplevel | None = None,
        _is_toplevel: bool = False,
    ) -> None:
        self.site = self._normalize_site(site)
        self.window_size = self._normalize_size(window_size)
        self.title = title or "WebView Tkinter"
        self.min_size = self._normalize_size(min_size, allow_none=True)
        self.max_size = self._normalize_size(max_size, allow_none=True)
        self.position = self._normalize_point(position)
        self.resizable = self._normalize_resizable(resizable)
        self.fullscreen = fullscreen
        self.topmost = topmost
        self.transparent_color = transparent_color
        self.alpha = self._normalize_alpha(alpha)
        self.background = background
        self.icon_path = self._normalize_optional_path(icon_path)
        self.overrideredirect_enabled = overrideredirect
        self.center = center
        self.window_options = dict(window_options or {})
        self.attributes = dict(attributes or {})
        self.root: tk.Tk | tk.Toplevel | None = None
        self.browser: TkWebview | None = None
        self._parent_root = _parent_root
        self._is_toplevel = _is_toplevel
        self._child_windows: list["WebViewWindow"] = []
        self._icon_image: tk.PhotoImage | None = None
        self._home_site = self.site
        self._bridge_scripts: dict[str, str] = {}
        self._exposed_functions: dict[str, tuple[object, bool]] = {}
        self._open_access_expose_rules: set[str] = set()
        self._open_access_site_rules: set[str] = set()
        self._frontend_call_state = threading.local()
        self.expose_function = FunctionBridge(self)

        app._bind(self)
        self._install_bridge_script("bridge_core", self._get_bridge_core_script())

    def _get_bridge_core_script(self) -> str:
        return """
window.send = window.send || {};
window.receive = window.receive || {};
window.__webviewTkinterReceive = window.__webviewTkinterReceive || {};
window.__webviewTkinterEmit = (name, params) => {
  const callback = window.__webviewTkinterReceive[name];
  if (typeof callback === "function") {
    return callback(params);
  }
  return null;
};
"""

    def _normalize_site(self, site: str) -> str:
        if not isinstance(site, str) or not site.strip():
            raise ValueError("site must be a valid URL or local file path.")

        site = site.strip()
        if "://" in site:
            return site

        local_path = Path(site).expanduser().resolve()
        if local_path.exists():
            return local_path.as_uri()

        raise ValueError(
            "site must start with http://, https://, or point to an existing local file."
        )

    def _normalize_optional_path(self, path: str | None) -> str | None:
        if path is None:
            return None

        resolved = Path(path).expanduser().resolve()
        if not resolved.exists():
            raise ValueError(f"Path not found: {resolved}")
        return str(resolved)

    def _normalize_lock_target(self, target: str) -> str:
        if not isinstance(target, str) or not target.strip():
            raise ValueError("Each access rule must be a valid URL or file path.")

        target = target.strip()
        if "://" in target:
            parsed = urlparse(target)
            if parsed.scheme.lower() == "file":
                return self._file_url_to_uri(parsed.path or "")
            normalized_path = unquote(parsed.path or "")
            return f"{parsed.scheme.lower()}://{(parsed.netloc or '').lower()}{normalized_path}"

        resolved = Path(target).expanduser().resolve()
        return resolved.as_uri()

    def _file_url_to_uri(self, raw_path: str) -> str:
        normalized_path = unquote(raw_path or "")
        if len(normalized_path) >= 3 and normalized_path[0] == "/" and normalized_path[2] == ":":
            normalized_path = normalized_path[1:]
        return Path(normalized_path).resolve().as_uri()

    def _normalize_request_origin(self, href: str) -> str:
        parsed = urlparse(href)
        if parsed.scheme == "file":
            return self._file_url_to_uri(parsed.path or "")

        normalized_path = unquote(parsed.path or "")
        return f"{parsed.scheme.lower()}://{(parsed.netloc or '').lower()}{normalized_path}"

    def _normalize_access_sources(
        self, allowed_sources: list[str] | tuple[str, ...] | set[str]
    ) -> set[str]:
        if not isinstance(allowed_sources, (list, tuple, set)):
            raise TypeError(
                "Access rules must be provided as a list, tuple, or set of URLs/paths."
            )

        return {self._normalize_lock_target(source) for source in allowed_sources}

    def _normalize_size(
        self,
        size: tuple[int, int] | list[int] | None,
        *,
        allow_none: bool = False,
    ) -> tuple[int, int] | None:
        if size is None:
            if allow_none:
                return None
            return (1200, 800)

        if not isinstance(size, Iterable):
            raise TypeError("Size must be a tuple/list with width and height.")

        values = list(size)
        if len(values) != 2:
            raise ValueError("Size must contain exactly two values.")

        width, height = values
        if not isinstance(width, int) or not isinstance(height, int):
            raise TypeError("Size values must be integers.")

        if width <= 0 or height <= 0:
            raise ValueError("Size values must be greater than zero.")

        return (width, height)

    def _normalize_point(
        self, point: tuple[int, int] | list[int] | None
    ) -> tuple[int, int] | None:
        if point is None:
            return None

        if not isinstance(point, Iterable):
            raise TypeError("position must be a tuple/list with x and y.")

        values = list(point)
        if len(values) != 2:
            raise ValueError("position must contain exactly two values.")

        pos_x, pos_y = values
        if not isinstance(pos_x, int) or not isinstance(pos_y, int):
            raise TypeError("position values must be integers.")

        return (pos_x, pos_y)

    def _normalize_alpha(self, alpha: float | None) -> float | None:
        if alpha is None:
            return None

        if not isinstance(alpha, (int, float)):
            raise TypeError("alpha must be a number between 0.0 and 1.0.")

        alpha = float(alpha)
        if not 0.0 <= alpha <= 1.0:
            raise ValueError("alpha must be between 0.0 and 1.0.")

        return alpha

    def _normalize_resizable(
        self, resizable: tuple[bool, bool] | list[bool] | bool
    ) -> tuple[bool, bool]:
        if isinstance(resizable, bool):
            return (resizable, resizable)

        if not isinstance(resizable, Iterable):
            raise TypeError("resizable must be a bool or a tuple/list with two bools.")

        values = list(resizable)
        if len(values) != 2:
            raise ValueError("resizable must contain exactly two values.")

        width, height = values
        if not isinstance(width, bool) or not isinstance(height, bool):
            raise TypeError("resizable values must be bool.")

        return (width, height)

    def _run_on_tk_thread(self, callback, *args):
        if self.root is None or threading.current_thread() is threading.main_thread():
            return callback(*args)

        done = threading.Event()
        result: dict[str, object] = {}

        def runner() -> None:
            try:
                result["value"] = callback(*args)
            except Exception as exc:
                result["error"] = exc
            finally:
                done.set()

        self.root.after(0, runner)
        done.wait()

        if "error" in result:
            raise result["error"]  # type: ignore[misc]

        return result.get("value")

    @contextmanager
    def _frontend_callback_guard(self, allow_unsafe_js: bool):
        previous_state = getattr(self._frontend_call_state, "active", False)
        previous_unsafe = getattr(self._frontend_call_state, "allow_unsafe_js", False)
        self._frontend_call_state.active = True
        self._frontend_call_state.allow_unsafe_js = allow_unsafe_js
        try:
            yield
        finally:
            self._frontend_call_state.active = previous_state
            self._frontend_call_state.allow_unsafe_js = previous_unsafe

    def _invoke_callback(self, callback, *args):
        try:
            signature = inspect.signature(callback)
        except (TypeError, ValueError):
            return callback(*args)

        parameters = list(signature.parameters.values())
        has_varargs = any(
            parameter.kind is inspect.Parameter.VAR_POSITIONAL
            for parameter in parameters
        )

        if has_varargs:
            return callback(*args)

        positional_parameters = [
            parameter
            for parameter in parameters
            if parameter.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        ]

        if len(positional_parameters) == 1:
            return callback(args)

        accepted_args = args[: len(positional_parameters)]
        return callback(*accepted_args)

    def _make_js_object_script(self, object_name: str, method_name: str, binding_name: str) -> str:
        return (
            f"window.{object_name} = window.{object_name} || {{}};"
            f"window.{object_name}.{method_name} = (...args) => window.send.{binding_name}(...args);"
        )

    def _make_receive_registration_script(self, name: str) -> str:
        return (
            f"window.receive = window.receive || {{}};"
            f"window.receive.{name} = (callback) => "
            f"window.__webviewTkinterReceive['{name}'] = callback;"
        )

    def _make_send_registration_script(self, name: str) -> str:
        return (
            f"window.send = window.send || {{}};"
            f"window.send.{name} = (...args) => "
            f"window.{name}({{__webview_tkinter_meta__: {{ href: window.location.href }} }}, ...args);"
        )

    def _get_site_access_guard_script(self) -> str:
        home_site = json.dumps(self._home_site, ensure_ascii=True)
        allowed_sites = json.dumps(sorted(self._open_access_site_rules), ensure_ascii=True)
        return f"""
window.__webviewTkinterAllowedSites = new Set({allowed_sites});
window.__webviewTkinterHomeSite = {home_site};
window.__webviewTkinterNormalizeUrl = (value) => {{
  try {{
    return new URL(value, window.location.href).href;
  }} catch (error) {{
    return String(value);
  }}
}};
window.__webviewTkinterCanOpen = (value) => {{
  const normalized = window.__webviewTkinterNormalizeUrl(value);
  return window.__webviewTkinterAllowedSites.has(normalized);
}};
window.__webviewTkinterRedirectHome = () => {{
  window.location.href = window.__webviewTkinterHomeSite;
}};
window.__webviewTkinterCheckAndOpen = (value) => {{
  if (window.__webviewTkinterCanOpen(value)) {{
    return true;
  }}
  alert("Access denied for this page.");
  window.__webviewTkinterRedirectHome();
  return false;
}};
document.addEventListener("click", (event) => {{
  const link = event.target.closest("a[href]");
  if (!link) {{
    return;
  }}
  if (!window.__webviewTkinterCheckAndOpen(link.href)) {{
    event.preventDefault();
  }}
}}, true);
const originalOpen = window.open.bind(window);
window.open = (...args) => {{
  if (!args.length || window.__webviewTkinterCheckAndOpen(args[0])) {{
    return originalOpen(...args);
  }}
  return null;
}};
const originalAssign = window.location.assign.bind(window.location);
window.location.assign = (value) => {{
  if (window.__webviewTkinterCheckAndOpen(value)) {{
    return originalAssign(value);
  }}
}};
const originalReplace = window.location.replace.bind(window.location);
window.location.replace = (value) => {{
  if (window.__webviewTkinterCheckAndOpen(value)) {{
    return originalReplace(value);
  }}
}};
"""

    def _install_bridge_script(self, script_id: str, script: str) -> None:
        self._bridge_scripts[script_id] = script

        if self.browser is not None:
            self.browser.init(script)
            self.browser.eval(script)

    def _register_pending_bindings(self) -> None:
        if self.browser is None:
            return

        for name, (callback, is_async_return) in self._exposed_functions.items():
            self.browser.bindjs(name, callback, is_async_return=is_async_return)

        for script in self._bridge_scripts.values():
            self.browser.init(script)

        if self._open_access_site_rules:
            self.browser.init(self._get_site_access_guard_script())

    def _apply_geometry(self) -> None:
        if self.root is None:
            return

        width, height = self.window_size
        geometry = f"{width}x{height}"

        if self.position is not None:
            pos_x, pos_y = self.position
            geometry = f"{geometry}+{pos_x}+{pos_y}"

        self.root.geometry(geometry)

        if self.center:
            self.root.update_idletasks()
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            pos_x = max((screen_width - width) // 2, 0)
            pos_y = max((screen_height - height) // 2, 0)
            self.root.geometry(f"{width}x{height}+{pos_x}+{pos_y}")

    def _apply_window_settings(self) -> None:
        if self.root is None:
            return

        self.root.title(self.title)
        self._apply_geometry()
        self.root.resizable(*self.resizable)

        if self.min_size is not None:
            self.root.minsize(*self.min_size)

        if self.max_size is not None:
            self.root.maxsize(*self.max_size)

        if self.background is not None:
            self.root.configure(bg=self.background)

        if self.icon_path is not None:
            icon_suffix = Path(self.icon_path).suffix.lower()
            if icon_suffix == ".ico":
                self.root.iconbitmap(self.icon_path)
            else:
                self._icon_image = tk.PhotoImage(file=self.icon_path)
                self.root.iconphoto(True, self._icon_image)

        self.root.overrideredirect(self.overrideredirect_enabled)

        if self.fullscreen:
            self.root.attributes("-fullscreen", True)

        if self.topmost:
            self.root.attributes("-topmost", True)

        if self.transparent_color is not None:
            self.root.attributes("-transparentcolor", self.transparent_color)

        if self.alpha is not None:
            self.root.attributes("-alpha", self.alpha)

        for attribute_name, value in self.attributes.items():
            self.root.attributes(attribute_name, value)

        if self.window_options:
            self.root.configure(**self.window_options)

    def _build_init_kwargs(self) -> dict[str, object]:
        return {
            "site": self.site,
            "window_size": self.window_size,
            "title": self.title,
            "min_size": self.min_size,
            "max_size": self.max_size,
            "position": self.position,
            "center": self.center,
            "resizable": self.resizable,
            "fullscreen": self.fullscreen,
            "topmost": self.topmost,
            "transparent_color": self.transparent_color,
            "alpha": self.alpha,
            "background": self.background,
            "icon_path": self.icon_path,
            "overrideredirect": self.overrideredirect_enabled,
            "window_options": dict(self.window_options),
            "attributes": dict(self.attributes),
        }

    def create_window(self) -> tk.Tk | tk.Toplevel:
        if self._is_toplevel:
            if self._parent_root is None:
                raise RuntimeError("Toplevel windows require an existing parent window.")
            self.root = tk.Toplevel(self._parent_root)
        else:
            self.root = tk.Tk()
        self._apply_window_settings()

        try:
            self.browser = TkWebview(self.root)
        except Exception as exc:
            if self.root is not None:
                self.root.destroy()
                self.root = None
            raise RuntimeError(
                "Failed to start WebView2. Make sure Microsoft Edge WebView2 Runtime is installed on Windows."
            ) from exc

        self.browser.pack(fill="both", expand=True)
        self._register_pending_bindings()
        self.browser.navigate(self.site)

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        return self.root

    def topLevel(
        self,
        site: str | None = None,
        window_size: tuple[int, int] | list[int] | None = None,
        title: str | None = None,
        **window_kwargs,
    ) -> "WebViewWindow":
        if self.root is None:
            self.create_window()

        child_kwargs = self._build_init_kwargs()
        child_kwargs.update(window_kwargs)

        if site is not None:
            child_kwargs["site"] = site
        if window_size is not None:
            child_kwargs["window_size"] = window_size
        if title is not None:
            child_kwargs["title"] = title

        child_kwargs["_parent_root"] = self.root
        child_kwargs["_is_toplevel"] = True

        child_window = WebViewWindow(**child_kwargs)
        child_window._open_access_expose_rules = set(self._open_access_expose_rules)
        child_window._open_access_site_rules = set(self._open_access_site_rules)
        child_window._exposed_functions = dict(self._exposed_functions)
        child_window._bridge_scripts = dict(self._bridge_scripts)
        child_window.run()
        self._child_windows.append(child_window)
        return child_window

    def _register_receive_function(
        self,
        name: str,
        callback,
        *,
        run_on_ui_thread: bool = True,
        allow_unsafe_js: bool = False,
    ) -> None:
        if not name.isidentifier():
            raise ValueError("The exposed function name must be a valid identifier.")
        if not callable(callback):
            raise TypeError("callback must be a callable function or method.")

        def wrapped(*args):
            request_origin = None
            payload_args = args

            if payload_args and isinstance(payload_args[0], dict):
                meta = payload_args[0].get("__webview_tkinter_meta__")
                if isinstance(meta, dict):
                    request_origin = meta.get("href")
                    payload_args = payload_args[1:]

            self._assert_origin_allowed(request_origin)

            def guarded_invoke():
                with self._frontend_callback_guard(allow_unsafe_js):
                    return self._invoke_callback(callback, *payload_args)

            if run_on_ui_thread:
                return self._run_on_tk_thread(guarded_invoke)
            return guarded_invoke()

        self._exposed_functions[name] = (wrapped, False)

        if self.browser is not None:
            self.browser.bindjs(name, wrapped, is_async_return=False)

        self._install_bridge_script(f"send_{name}", self._make_send_registration_script(name))
        self._install_bridge_script(f"receive_{name}", self._make_receive_registration_script(name))

    def _assert_origin_allowed(self, request_origin: str | None) -> None:
        if not self._open_access_expose_rules:
            return

        if not request_origin:
            raise PermissionError("Bridge blocked: page origin could not be identified.")

        normalized_origin = self._normalize_request_origin(request_origin)
        if normalized_origin not in self._open_access_expose_rules:
            raise PermissionError(f"Bridge blocked for this origin: {normalized_origin}")

    def _emit_to_frontend(self, name: str, *args) -> None:
        serialized_args = json.dumps(list(args), ensure_ascii=True)
        script = f"window.__webviewTkinterEmit('{name}', {serialized_args});"
        self.evaluate_js(script)

    def openAccessExpose(
        self, allowed_sources: list[str] | tuple[str, ...] | set[str]
    ) -> None:
        self._open_access_expose_rules = self._normalize_access_sources(allowed_sources)

    def openAccessSite(
        self, allowed_sources: list[str] | tuple[str, ...] | set[str]
    ) -> None:
        normalized = self._normalize_access_sources(allowed_sources)
        normalized.add(self._home_site)
        self._open_access_site_rules = normalized
        self._install_bridge_script("site_access_guard", self._get_site_access_guard_script())

    def lock(self, allowed_sources: list[str] | tuple[str, ...] | set[str]) -> None:
        self.openAccessExpose(allowed_sources)

    def navigate(self, site: str) -> None:
        normalized_site = self._normalize_site(site)

        if self._open_access_site_rules and normalized_site not in self._open_access_site_rules:
            if self.browser is not None:
                self.browser.navigate(self._home_site)
            raise PermissionError(f"Site blocked by openAccessSite(): {normalized_site}")

        self.site = normalized_site
        if self.browser is not None:
            self.browser.navigate(self.site)

    def expose_object(
        self,
        object_name: str,
        instance: object,
        methods: list[str] | tuple[str, ...] | None = None,
        *,
        run_on_ui_thread: bool = True,
    ) -> None:
        if not object_name.isidentifier():
            raise ValueError("The exposed object name must be a valid identifier.")

        if methods is None:
            methods = [
                method_name
                for method_name in dir(instance)
                if not method_name.startswith("_") and callable(getattr(instance, method_name))
            ]

        for method_name in methods:
            method = getattr(instance, method_name)
            if not callable(method):
                raise TypeError(f"{method_name} is not a callable method.")

            binding_name = f"{object_name}_{method_name}"
            self.expose_function.receive(
                binding_name,
                method,
                run_on_ui_thread=run_on_ui_thread,
            )
            self._install_bridge_script(
                binding_name,
                self._make_js_object_script(object_name, method_name, binding_name),
            )

    def set_title(self, title: str) -> None:
        self.title = title
        if self.root is not None:
            self.root.title(title)

    def set_window_size(self, width: int, height: int) -> None:
        self.window_size = self._normalize_size((width, height))
        if self.root is not None:
            self._apply_geometry()

    def set_position(self, x: int, y: int) -> None:
        self.position = self._normalize_point((x, y))
        self.center = False
        if self.root is not None:
            self._apply_geometry()

    def set_fullscreen(self, enabled: bool) -> None:
        self.fullscreen = enabled
        if self.root is not None:
            self.root.attributes("-fullscreen", enabled)

    def set_topmost(self, enabled: bool) -> None:
        self.topmost = enabled
        if self.root is not None:
            self.root.attributes("-topmost", enabled)

    def reload(self) -> None:
        if self.browser is not None:
            self.browser.reload()

    def go_back(self) -> None:
        if self.browser is not None:
            self.browser.go_back()

    def go_forward(self) -> None:
        if self.browser is not None:
            self.browser.go_forward()

    def evaluate_js(self, script: str) -> None:
        is_frontend_call = getattr(self._frontend_call_state, "active", False)
        allow_unsafe_js = getattr(self._frontend_call_state, "allow_unsafe_js", False)
        if is_frontend_call and not allow_unsafe_js:
            raise RuntimeError(
                "evaluate_js() was blocked during a frontend-triggered callback. "
                "Use expose_function.send(...) or unsafe_evaluate_js(...)."
            )

        if self.browser is not None:
            self.browser.eval(script)

    def unsafe_evaluate_js(self, script: str) -> None:
        if self.browser is not None:
            self.browser.eval(script)

    def close(self) -> None:
        for child_window in list(self._child_windows):
            child_window.close()
        self._child_windows.clear()

        if self.browser is not None:
            self.browser.destroy_webview()
            self.browser = None

        if self.root is not None:
            self.root.destroy()
            self.root = None

    def run(self) -> None:
        if self.root is None:
            self.create_window()

        if self.root is not None and not self._is_toplevel:
            self.root.mainloop()


def open_webview(
    site: str,
    window_size: tuple[int, int] | list[int] | None = None,
    title: str | None = None,
    **window_kwargs,
) -> None:
    current_app = WebViewWindow(
        site=site,
        window_size=window_size,
        title=title,
        **window_kwargs,
    )
    current_app.run()
