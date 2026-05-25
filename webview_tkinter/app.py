from __future__ import annotations

import inspect
import importlib.util
import json
import threading
import tkinter as tk
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urlparse

try:
    import pystray
except ImportError:
    pystray = None
from tkwebview import TkWebview
from tkwebview.core import Webview
try:
    from PIL import Image, ImageDraw
except ImportError:
    Image = None
    ImageDraw = None


class ConfigurableTkWebview(tk.Frame):
    def __init__(self, master=None, *, debug: bool = False, **kwargs):
        if master is None:
            raise ValueError("ConfigurableTkWebview requires a Tkinter master window.")

        super().__init__(master, bg="black", **kwargs)
        self.update()
        self.webview = Webview(debug=debug, window=self.winfo_id())
        self.bind("<Configure>", self.on_configure)

    def on_configure(self, event):
        self.webview.resize()

    def bindjs(self, name, fn, is_async_return=False):
        return self.webview.bind(name, fn, is_async_return)

    def eval(self, js):
        return self.webview.eval(js)

    def navigate(self, url):
        return self.webview.navigate(url)

    def init(self, js):
        return self.webview.init(js)

    def set_html(self, html):
        return self.webview.set_html(html)

    def destroy_webview(self):
        self.destroy()

    def reload(self):
        return self.webview.reload()

    def go_back(self):
        return self.webview.go_back()

    def go_forward(self):
        return self.webview.go_forward()


def _load_frontend_assets() -> tuple[dict[str, dict[str, object]], set[str]]:
    frontend_path = Path(__file__).resolve().parent.parent / "frontend.py"
    if not frontend_path.exists():
        return {}, set()

    spec = importlib.util.spec_from_file_location("_webview_tkinter_frontend_assets", frontend_path)
    if spec is None or spec.loader is None:
        return {}, set()

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assets = getattr(module, "ASSET_INDEX", {})
    asset_names = set(getattr(module, "ASSET_NAMES", []))
    if not isinstance(assets, dict):
        return {}, set()
    return assets, asset_names


FRONTEND_ASSETS, FRONTEND_ASSET_NAMES = _load_frontend_assets()


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


class SystemTrayController:
    def __init__(self, window: "WebViewWindow") -> None:
        self.window = window

    def __call__(
        self,
        enabled: bool = True,
        *,
        icon_path: str | None = None,
        tooltip: str | None = None,
        close_to_tray: bool = True,
        allow_restore: bool = True,
        allow_quit: bool = True,
        menu_items: list[dict[str, object]] | tuple[dict[str, object], ...] | None = None,
    ) -> None:
        self.window._configure_system_tray(
            enabled=enabled,
            icon_path=icon_path,
            tooltip=tooltip,
            close_to_tray=close_to_tray,
            allow_restore=allow_restore,
            allow_quit=allow_quit,
            menu_items=menu_items,
        )

    def alert(
        self,
        site: str,
        *,
        window_size: tuple[int, int] | list[int] | None = (420, 240),
        title: str | None = None,
        padding: tuple[int, int] | list[int] | None = (24, 56),
        margin: tuple[int, int] | list[int] | None = (24, 56),
        duration_ms: int | None = None,
        close_buttom: bool = False,
        close_button: bool | None = None,
        events=None,
        **window_kwargs,
    ) -> "WebViewWindow":
        return self.window._show_system_tray_alert(
            site=site,
            window_size=window_size,
            title=title,
            padding=padding,
            margin=margin,
            duration_ms=duration_ms,
            close_buttom=close_buttom,
            close_button=close_button,
            events=events,
            **window_kwargs,
        )

    def restore(self) -> None:
        self.window.restore_from_system_tray()

    def minimize(self) -> None:
        self.window.minimize_to_system_tray()

    def close(self) -> None:
        self.window.close()


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
        events=None,
        _parent_root: tk.Tk | tk.Toplevel | None = None,
        _is_top_level: bool = False,
        _debug_mode_enabled: bool = False,
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
        self._events_callback = self._normalize_events_callback(events)
        self.root: tk.Tk | tk.Toplevel | None = None
        self.browser: ConfigurableTkWebview | TkWebview | None = None
        self._parent_root = _parent_root
        self._is_top_level = _is_top_level
        self._child_windows: list["WebViewWindow"] = []
        self._icon_image: tk.PhotoImage | None = None
        self._home_site = self.site
        self._current_asset_name = self._asset_name_from_site(self.site)
        self._bridge_scripts: dict[str, str] = {}
        self._exposed_functions: dict[str, tuple[object, bool]] = {}
        self._open_access_expose_rules: set[str] = set()
        self._open_access_site_rules: set[str] = set()
        self._frontend_call_state = threading.local()
        self._debug_mode_enabled = _debug_mode_enabled
        self._last_window_state: str | None = None
        self._last_window_geometry: tuple[int, int, int, int] | None = None
        self._close_event_emitted = False
        self._system_tray_enabled = False
        self._system_tray_close_to_tray = True
        self._system_tray_icon_path: str | None = None
        self._system_tray_tooltip: str | None = None
        self._system_tray_allow_quit = True
        self._system_tray_allow_restore = True
        self._system_tray_menu_items: list[dict[str, object]] = []
        self._tray_icon: pystray.Icon | None = None
        self._tray_thread: threading.Thread | None = None
        self._is_in_system_tray = False
        self.expose_function = FunctionBridge(self)
        self.system_tray = SystemTrayController(self)
        self.SystemTray = self.system_tray

        app._bind(self)
        self._install_bridge_script("bridge_core", self._get_bridge_core_script())
        self._install_bridge_script("debug_runtime", self._get_debug_runtime_script())

    def _get_bridge_core_script(self) -> str:
        return """
window.send = window.send || {};
window.receive = window.receive || {};
window.__webviewTkinterReceive = window.__webviewTkinterReceive || {};
window.__webviewTkinterCurrentAsset = null;
window.__webviewTkinterDebugMode = false;
window.__webviewTkinterEmit = (name, params) => {
  const callback = window.__webviewTkinterReceive[name];
  if (typeof callback === "function") {
    return callback(params);
  }
  return null;
};
"""

    def _get_debug_runtime_script(self) -> str:
        debug_mode = "true" if self._debug_mode_enabled else "false"
        return f"""
window.__webviewTkinterDebugMode = {debug_mode};
window.__webviewTkinterApplyDebugMode = () => {{
  const existingStyle = document.getElementById("__webviewTkinterDebugStyle");
  if (existingStyle) {{
    existingStyle.remove();
  }}
  if (window.__webviewTkinterDebugMode) {{
    return;
  }}

  const style = document.createElement("style");
  style.id = "__webviewTkinterDebugStyle";
  style.textContent = `
    html, body {{
      -webkit-user-select: none;
      user-select: none;
      -webkit-touch-callout: none;
    }}
  `;
  document.documentElement.appendChild(style);
}};
window.__webviewTkinterHandleDebugBlock = (event) => {{
  if (window.__webviewTkinterDebugMode) {{
    return;
  }}

  const blockedKey =
    event.key === "F12" ||
    (event.ctrlKey && event.shiftKey && ["I", "J", "C", "K"].includes((event.key || "").toUpperCase())) ||
    (event.ctrlKey && ["U", "S", "P"].includes((event.key || "").toUpperCase()));

  if (blockedKey) {{
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
  }}
}};
if (!window.__webviewTkinterDebugBindingsInstalled) {{
  document.addEventListener("contextmenu", (event) => {{
    if (!window.__webviewTkinterDebugMode) {{
      event.preventDefault();
    }}
  }}, true);
  document.addEventListener("keydown", window.__webviewTkinterHandleDebugBlock, true);
  document.addEventListener("dragstart", (event) => {{
    if (!window.__webviewTkinterDebugMode) {{
      event.preventDefault();
    }}
  }}, true);
  document.addEventListener("selectstart", (event) => {{
    if (!window.__webviewTkinterDebugMode) {{
      event.preventDefault();
    }}
  }}, true);
  window.__webviewTkinterDebugBindingsInstalled = true;
}}
if (document.readyState === "loading") {{
  document.addEventListener("DOMContentLoaded", window.__webviewTkinterApplyDebugMode, {{ once: true }});
}} else {{
  window.__webviewTkinterApplyDebugMode();
}}
"""

    def _get_alert_close_button_script(self) -> str:
        return """
window.__webviewTkinterInstallAlertCloseButton = () => {
  if (document.getElementById("__webviewTkinterAlertClose")) {
    return;
  }

  const style = document.createElement("style");
  style.id = "__webviewTkinterAlertCloseStyle";
  style.textContent = `
    .__webviewTkinterAlertCloseButton {
      position: fixed;
      top: 10px;
      right: 10px;
      width: 32px;
      height: 32px;
      border: 0;
      border-radius: 999px;
      background: rgba(15, 23, 42, 0.88);
      color: #e2e8f0;
      font-size: 18px;
      line-height: 1;
      cursor: pointer;
      z-index: 2147483647;
      box-shadow: 0 10px 24px rgba(15, 23, 42, 0.26);
    }
  `;
  document.documentElement.appendChild(style);

  const button = document.createElement("button");
  button.id = "__webviewTkinterAlertClose";
  button.className = "__webviewTkinterAlertCloseButton";
  button.type = "button";
  button.setAttribute("aria-label", "Close alert");
  button.textContent = "×";
  button.addEventListener("click", () => {
    if (typeof window.__webview_tkinter_close_alert === "function") {
      window.__webview_tkinter_close_alert({
        __webview_tkinter_meta__: {
          href: window.location.href,
          asset: window.__webviewTkinterCurrentAsset
        }
      });
    }
  });
  document.body.appendChild(button);
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", window.__webviewTkinterInstallAlertCloseButton, { once: true });
} else {
  window.__webviewTkinterInstallAlertCloseButton();
}
"""

    def _normalize_site(self, site: str) -> str:
        if not isinstance(site, str) or not site.strip():
            raise ValueError("site must be a valid URL or local file path.")

        site = site.strip()
        asset_uri = self._asset_name_to_uri(site)
        if asset_uri is not None:
            return asset_uri

        if "://" in site:
            return site

        local_path = Path(site).expanduser().resolve()
        if local_path.exists():
            return local_path.as_uri()

        raise ValueError(
            "site must start with http://, https://, or point to an existing local file."
        )

    def _asset_name_to_uri(self, site: str) -> str | None:
        normalized_name = site.strip().replace("\\", "/")
        if normalized_name in FRONTEND_ASSET_NAMES:
            return f"asset://{normalized_name}"
        return None

    def _asset_name_from_site(self, site: str) -> str | None:
        if site.startswith("asset://"):
            return site.removeprefix("asset://")
        return None

    def _is_asset_site(self, site: str) -> bool:
        return self._asset_name_from_site(site) is not None

    def _normalize_asset_reference(self, target: str) -> str | None:
        normalized = target.strip().replace("\\", "/")
        if normalized in FRONTEND_ASSET_NAMES:
            return self._asset_name_to_uri(normalized)
        return None

    def _normalize_optional_path(self, path: str | None) -> str | None:
        if path is None:
            return None

        resolved = Path(path).expanduser().resolve()
        if not resolved.exists():
            raise ValueError(f"Path not found: {resolved}")
        return str(resolved)

    def _normalize_events_callback(self, events):
        if events is None:
            return None
        if not callable(events):
            raise TypeError("events must be a callable function or method.")
        return events

    def _normalize_system_tray_menu_items(self, menu_items) -> list[dict[str, object]]:
        if menu_items is None:
            return []
        if not isinstance(menu_items, (list, tuple)):
            raise TypeError("menu_items must be a list or tuple of dictionaries.")

        normalized_items: list[dict[str, object]] = []
        for item in menu_items:
            if not isinstance(item, dict):
                raise TypeError("Each tray menu item must be a dictionary.")

            label = item.get("label")
            callback = item.get("callback")
            default = bool(item.get("default", False))
            enabled = bool(item.get("enabled", True))

            if not isinstance(label, str) or not label.strip():
                raise ValueError("Each tray menu item needs a non-empty 'label'.")
            if not callable(callback):
                raise TypeError("Each tray menu item needs a callable 'callback'.")

            normalized_items.append(
                {
                    "label": label.strip(),
                    "callback": callback,
                    "default": default,
                    "enabled": enabled,
                }
            )
        return normalized_items

    def _normalize_lock_target(self, target: str) -> str:
        if not isinstance(target, str) or not target.strip():
            raise ValueError("Each access rule must be a valid URL or file path.")

        target = target.strip()
        asset_uri = self._normalize_asset_reference(target)
        if asset_uri is not None:
            return asset_uri

        if "://" in target:
            parsed = urlparse(target)
            if parsed.scheme.lower() == "file":
                return self._file_url_to_uri(parsed.path or "")
            if parsed.scheme.lower() == "asset":
                return f"asset://{unquote((parsed.netloc or '') + (parsed.path or '')).lstrip('/')}"
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
        asset_uri = self._normalize_asset_reference(href)
        if asset_uri is not None:
            return asset_uri

        if href.startswith("asset://"):
            return href

        parsed = urlparse(href)
        if parsed.scheme == "about" and (parsed.path or "").lower() == "blank":
            if self._current_asset_name is not None:
                return f"asset://{self._current_asset_name}"
            return "about:blank"

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
            f"window.{name}({{__webview_tkinter_meta__: {{ "
            f"href: window.location.href, asset: window.__webviewTkinterCurrentAsset "
            f"}} }}, ...args);"
        )

    def _get_site_access_guard_script(self) -> str:
        home_site = json.dumps(self._home_site, ensure_ascii=True)
        allowed_sites = json.dumps(sorted(self._open_access_site_rules), ensure_ascii=True)
        known_assets = json.dumps(sorted(FRONTEND_ASSET_NAMES), ensure_ascii=True)
        return f"""
window.__webviewTkinterKnownAssets = new Set({known_assets});
window.__webviewTkinterAllowedSites = new Set({allowed_sites});
window.__webviewTkinterHomeSite = {home_site};
window.__webviewTkinterResolveAssetPath = (value) => {{
  if (!window.__webviewTkinterCurrentAsset || !value) {{
    return null;
  }}
  if (/^(https?:|file:|data:|javascript:|mailto:|tel:)/i.test(value)) {{
    return null;
  }}
  const currentAsset = window.__webviewTkinterCurrentAsset || "";
  const currentDir = currentAsset.includes("/") ? currentAsset.slice(0, currentAsset.lastIndexOf("/") + 1) : "";
  try {{
    const url = new URL(value, "https://webview.local/" + currentDir);
    const normalized = url.pathname.replace(/^\\//, "");
    if (window.__webviewTkinterKnownAssets.has(normalized)) {{
      return normalized;
    }}
  }} catch (error) {{
    return null;
  }}
  return null;
}};
window.__webviewTkinterNormalizeUrl = (value) => {{
  const assetTarget = window.__webviewTkinterResolveAssetPath(value);
  if (assetTarget) {{
    return "asset://" + assetTarget;
  }}
  try {{
    return new URL(value, window.location.href).href;
  }} catch (error) {{
    return String(value);
  }}
}};
window.__webviewTkinterCanOpen = (value) => {{
  const normalized = window.__webviewTkinterNormalizeUrl(value);
  return !window.__webviewTkinterAllowedSites.size || window.__webviewTkinterAllowedSites.has(normalized);
}};
window.__webviewTkinterRedirectHome = () => {{
  if ((window.__webviewTkinterHomeSite || "").startsWith("asset://")) {{
    return window.__webview_tkinter_asset_navigate(
      window.__webviewTkinterHomeSite.replace(/^asset:\\/\\//, "")
    );
  }}
  window.location.href = window.__webviewTkinterHomeSite;
}};
window.__webviewTkinterCheckAndOpen = (value) => {{
  const assetTarget = window.__webviewTkinterResolveAssetPath(value);
  if (window.__webviewTkinterCanOpen(value)) {{
    if (assetTarget) {{
      window.__webview_tkinter_asset_navigate(assetTarget);
      return false;
    }}
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
  if (!window.__webviewTkinterCheckAndOpen(link.getAttribute("href") || link.href)) {{
    event.preventDefault();
  }}
}}, true);
const originalOpen = window.open.bind(window);
window.open = (...args) => {{
  if (!args.length) {{
    return originalOpen(...args);
  }}
  if (window.__webviewTkinterCheckAndOpen(args[0])) {{
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

    def _get_asset_navigation_script(self, asset_name: str) -> str:
        asset_name_literal = json.dumps(asset_name, ensure_ascii=True)
        asset_names_literal = json.dumps(sorted(FRONTEND_ASSET_NAMES), ensure_ascii=True)
        allowed_sites_literal = json.dumps(sorted(self._open_access_site_rules), ensure_ascii=True)
        home_site_literal = json.dumps(self._home_site, ensure_ascii=True)
        return f"""
window.__webviewTkinterCurrentAsset = {asset_name_literal};
window.__webviewTkinterKnownAssets = new Set({asset_names_literal});
window.__webviewTkinterAllowedSites = new Set({allowed_sites_literal});
window.__webviewTkinterHomeSite = {home_site_literal};
"""

    def _inject_runtime_script(self, html: str, script: str) -> str:
        script_tag = f"<script>\n{script}\n</script>"
        if "</head>" in html:
            return html.replace("</head>", f"{script_tag}\n</head>", 1)
        if "<body" in html and ">" in html:
            body_start = html.find(">")
            if body_start != -1:
                return f"{html[:body_start + 1]}\n{script_tag}\n{html[body_start + 1:]}"
        return f"{script_tag}\n{html}"

    def _load_current_site(self) -> None:
        if self.browser is None:
            return

        asset_name = self._asset_name_from_site(self.site)
        self._current_asset_name = asset_name

        if asset_name is not None:
            asset = FRONTEND_ASSETS.get(asset_name)
            if asset is None:
                raise FileNotFoundError(f"Bundled frontend asset not found: {asset_name}")
            embedded_html = str(asset["embedded_html"])
            runtime_script = self._get_asset_navigation_script(asset_name)
            self.browser.set_html(self._inject_runtime_script(embedded_html, runtime_script))
            return

        self.browser.navigate(self.site)

    def _register_pending_bindings(self) -> None:
        if self.browser is None:
            return

        self.browser.bindjs("__webview_tkinter_asset_navigate", self._handle_asset_navigation, is_async_return=False)

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
            "events": self._events_callback,
            "_debug_mode_enabled": self._debug_mode_enabled,
        }

    def _create_child_window(
        self,
        *,
        site: str,
        window_size: tuple[int, int] | list[int] | None = None,
        title: str | None = None,
        additional_allowed_sources: list[str] | tuple[str, ...] | set[str] | None = None,
        configure_window=None,
        **window_kwargs,
    ) -> "WebViewWindow":
        if self.root is None:
            self.create_window()

        child_kwargs = self._build_init_kwargs()
        child_kwargs.update(window_kwargs)

        child_kwargs["site"] = site
        if window_size is not None:
            child_kwargs["window_size"] = window_size
        if title is not None:
            child_kwargs["title"] = title

        child_kwargs["_parent_root"] = self.root
        child_kwargs["_is_top_level"] = True

        child_window = WebViewWindow(**child_kwargs)
        child_window._open_access_expose_rules = set(self._open_access_expose_rules)
        child_window._open_access_site_rules = set(self._open_access_site_rules)
        child_window._exposed_functions = dict(self._exposed_functions)
        child_window._bridge_scripts = dict(self._bridge_scripts)
        child_window._system_tray_enabled = self._system_tray_enabled
        child_window._system_tray_close_to_tray = self._system_tray_close_to_tray
        child_window._system_tray_icon_path = self._system_tray_icon_path
        child_window._system_tray_tooltip = self._system_tray_tooltip
        child_window._system_tray_allow_quit = self._system_tray_allow_quit
        child_window._system_tray_allow_restore = self._system_tray_allow_restore
        child_window._system_tray_menu_items = list(self._system_tray_menu_items)

        if additional_allowed_sources:
            extra_sources = self._normalize_access_sources(additional_allowed_sources)
            child_window._open_access_expose_rules.update(extra_sources)
            child_window._open_access_site_rules.update(extra_sources)

        if configure_window is not None:
            configure_window(child_window)

        child_window.run()
        self._child_windows.append(child_window)
        return child_window

    def _show_system_tray_alert(
        self,
        *,
        site: str,
        window_size: tuple[int, int] | list[int] | None = (420, 240),
        title: str | None = None,
        padding: tuple[int, int] | list[int] | None = (24, 56),
        margin: tuple[int, int] | list[int] | None = (24, 56),
        duration_ms: int | None = None,
        close_buttom: bool = False,
        close_button: bool | None = None,
        events=None,
        **window_kwargs,
    ) -> "WebViewWindow":
        if not self._system_tray_enabled:
            raise RuntimeError("System tray alert requires system tray support to be enabled.")
        if self.root is None:
            raise RuntimeError("The main window must be created before showing a tray alert.")

        alert_size = self._normalize_size(window_size)
        alert_padding_source = padding if padding is not None else margin
        alert_padding = self._normalize_point(alert_padding_source) if alert_padding_source is not None else (24, 56)
        if alert_padding is None:
            alert_padding = (24, 56)
        show_close_button = close_buttom if close_button is None else close_button

        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        margin_x, margin_y = alert_padding
        width, height = alert_size
        pos_x = max(screen_width - width - margin_x, 0)
        pos_y = max(screen_height - height - margin_y, 0)

        def configure_alert_window(alert_window: "WebViewWindow") -> None:
            if show_close_button:
                alert_window.expose_function.receive(
                    "__webview_tkinter_close_alert",
                    lambda: alert_window.close(),
                )
                alert_window._install_bridge_script(
                    "alert_close_button",
                    self._get_alert_close_button_script(),
                )

        alert_window = self._create_child_window(
            site=site,
            window_size=alert_size,
            title=title or self.title,
            additional_allowed_sources=[site],
            configure_window=configure_alert_window,
            events=events,
            position=(pos_x, pos_y),
            topmost=True,
            resizable=(False, False),
            overrideredirect=window_kwargs.pop("overrideredirect", True),
            **window_kwargs,
        )

        if duration_ms is not None:
            if not isinstance(duration_ms, int) or duration_ms <= 0:
                raise ValueError("duration_ms must be a positive integer.")
            if alert_window.root is not None:
                alert_window.root.after(duration_ms, alert_window.close)

        return alert_window

    def _get_window_state(self) -> str | None:
        if self.root is None:
            return None
        try:
            state = self.root.state()
        except tk.TclError:
            return None
        return str(state).lower()

    def _get_window_geometry(self) -> tuple[int, int, int, int] | None:
        if self.root is None:
            return None
        try:
            return (
                int(self.root.winfo_x()),
                int(self.root.winfo_y()),
                int(self.root.winfo_width()),
                int(self.root.winfo_height()),
            )
        except tk.TclError:
            return None

    def _emit_window_event(self, event_name: str, **extra) -> None:
        if self._events_callback is None:
            return

        geometry = self._get_window_geometry()
        position = None
        size = None
        if geometry is not None:
            pos_x, pos_y, width, height = geometry
            position = {"x": pos_x, "y": pos_y}
            size = {"width": width, "height": height}

        payload = {
            "name": event_name,
            "title": self.title,
            "site": self.site,
            "asset": self._current_asset_name,
            "state": self._get_window_state(),
            "position": position,
            "size": size,
            "is_top_level": self._is_top_level,
        }
        payload.update(extra)

        try:
            self._events_callback(payload)
        except Exception:
            pass

    def _update_window_state(self, source: str) -> None:
        current_state = self._get_window_state()
        previous_state = self._last_window_state

        if current_state is None or current_state == previous_state:
            return

        self._last_window_state = current_state
        self._emit_window_event(
            "state_changed",
            source=source,
            previous_state=previous_state,
            current_state=current_state,
        )

        if current_state == "iconic":
            self._emit_window_event("minimized", source=source)
        elif current_state == "zoomed":
            self._emit_window_event("maximized", source=source)
        elif current_state == "normal" and previous_state in {"iconic", "zoomed"}:
            self._emit_window_event("restored", source=source)
        elif current_state == "withdrawn":
            self._emit_window_event("hidden", source=source)

    def _on_window_map(self, event) -> None:
        self._update_window_state("map")

    def _on_window_unmap(self, event) -> None:
        self._update_window_state("unmap")

    def _on_window_focus_in(self, event) -> None:
        self._emit_window_event("focus_in")

    def _on_window_focus_out(self, event) -> None:
        self._emit_window_event("focus_out")

    def _on_window_configure(self, event) -> None:
        geometry = self._get_window_geometry()
        previous_geometry = self._last_window_geometry
        if geometry is not None and previous_geometry is not None:
            prev_x, prev_y, prev_width, prev_height = previous_geometry
            pos_x, pos_y, width, height = geometry
            if (pos_x, pos_y) != (prev_x, prev_y):
                self._emit_window_event(
                    "moved",
                    previous_position={"x": prev_x, "y": prev_y},
                    current_position={"x": pos_x, "y": pos_y},
                )
            if (width, height) != (prev_width, prev_height):
                self._emit_window_event(
                    "resized",
                    previous_size={"width": prev_width, "height": prev_height},
                    current_size={"width": width, "height": height},
                )

        self._last_window_geometry = geometry
        self._update_window_state("configure")

    def _bind_window_events(self) -> None:
        if self.root is None:
            return

        self.root.bind("<Map>", self._on_window_map, add="+")
        self.root.bind("<Unmap>", self._on_window_unmap, add="+")
        self.root.bind("<FocusIn>", self._on_window_focus_in, add="+")
        self.root.bind("<FocusOut>", self._on_window_focus_out, add="+")
        self.root.bind("<Configure>", self._on_window_configure, add="+")

    def _handle_close_request(self) -> None:
        self._emit_window_event("close_requested")
        if self._system_tray_enabled and self._system_tray_close_to_tray:
            self.minimize_to_system_tray()
            return
        self.close()

    def debug_mode(self, enabled: bool = True) -> None:
        if not isinstance(enabled, bool):
            raise TypeError("debug_mode() expects a boolean value.")

        if self.browser is not None and enabled and not self._debug_mode_enabled:
            raise RuntimeError(
                "Enable debug_mode(True) before run() so the browser can be created with developer tools enabled."
            )

        self._debug_mode_enabled = enabled
        self._install_bridge_script("debug_runtime", self._get_debug_runtime_script())

        if self.browser is not None:
            self.evaluate_js(self._get_debug_runtime_script())

    def debugMode(self, enabled: bool = True) -> None:
        self.debug_mode(enabled)

    def _create_default_tray_image(self) -> Image.Image:
        if Image is None or ImageDraw is None:
            raise RuntimeError(
                "System tray support requires Pillow. Install dependencies from requirements.txt."
            )
        image = Image.new("RGBA", (64, 64), (15, 23, 42, 255))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((8, 8, 56, 56), radius=12, fill=(37, 99, 235, 255))
        draw.rectangle((20, 18, 44, 24), fill=(255, 255, 255, 255))
        draw.rectangle((20, 28, 44, 34), fill=(255, 255, 255, 220))
        draw.rectangle((20, 38, 36, 44), fill=(255, 255, 255, 180))
        return image

    def _load_tray_image(self) -> Image.Image:
        if self._system_tray_icon_path is not None:
            return Image.open(self._system_tray_icon_path)
        if self.icon_path is not None:
            return Image.open(self.icon_path)
        return self._create_default_tray_image()

    def _run_on_ui_thread_async(self, callback, *args) -> None:
        if self.root is None:
            callback(*args)
            return
        self.root.after(0, lambda: callback(*args))

    def _restore_from_tray(self, *_args) -> None:
        self._run_on_ui_thread_async(self.restore_from_system_tray)

    def _quit_from_tray(self, *_args) -> None:
        self._run_on_ui_thread_async(self.close)

    def _make_tray_menu(self):
        if pystray is None:
            raise RuntimeError(
                "System tray support requires pystray. Install dependencies from requirements.txt."
            )
        menu_entries = []

        if self._system_tray_allow_restore:
            menu_entries.append(
                pystray.MenuItem("Restore", self._restore_from_tray, default=True)
            )

        def make_menu_callback(current_callback):
            def wrapped(_icon, _item):
                self._run_on_ui_thread_async(current_callback, self)
            return wrapped

        for item in self._system_tray_menu_items:
            menu_entries.append(
                pystray.MenuItem(
                    str(item["label"]),
                    make_menu_callback(item["callback"]),
                    default=bool(item["default"]),
                    enabled=lambda _item, value=bool(item["enabled"]): value,
                )
            )

        if self._system_tray_allow_quit:
            menu_entries.append(pystray.MenuItem("Quit", self._quit_from_tray))

        return pystray.Menu(*menu_entries)

    def _ensure_tray_icon(self) -> None:
        if not self._system_tray_enabled or self._tray_icon is not None:
            return
        if pystray is None:
            raise RuntimeError(
                "System tray support requires pystray. Install dependencies from requirements.txt."
            )

        icon_image = self._load_tray_image()
        tooltip = self._system_tray_tooltip or self.title
        self._tray_icon = pystray.Icon(
            name=f"webview_tkinter_{id(self)}",
            title=tooltip,
            icon=icon_image,
            menu=self._make_tray_menu(),
        )

    def _start_tray_icon(self) -> None:
        self._ensure_tray_icon()
        if self._tray_icon is None:
            return
        if self._tray_thread is not None and self._tray_thread.is_alive():
            return

        def runner() -> None:
            self._tray_icon.run()

        self._tray_thread = threading.Thread(target=runner, daemon=True)
        self._tray_thread.start()

    def _stop_tray_icon(self) -> None:
        if self._tray_icon is not None:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
        self._tray_icon = None
        self._tray_thread = None

    def minimize_to_system_tray(self) -> None:
        if not self._system_tray_enabled or self.root is None:
            return

        self._start_tray_icon()
        self.root.withdraw()
        self._is_in_system_tray = True
        self._emit_window_event("tray_entered")

    def restore_from_system_tray(self) -> None:
        if self.root is None:
            return

        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self._is_in_system_tray = False
        self._emit_window_event("tray_restored")

    def _configure_system_tray(
        self,
        enabled: bool = True,
        *,
        icon_path: str | None = None,
        tooltip: str | None = None,
        close_to_tray: bool = True,
        allow_restore: bool = True,
        allow_quit: bool = True,
        menu_items: list[dict[str, object]] | tuple[dict[str, object], ...] | None = None,
    ) -> None:
        if not isinstance(enabled, bool):
            raise TypeError("system_tray() expects a boolean 'enabled' value.")
        if not isinstance(close_to_tray, bool):
            raise TypeError("close_to_tray must be a boolean value.")
        if not isinstance(allow_restore, bool):
            raise TypeError("allow_restore must be a boolean value.")
        if not isinstance(allow_quit, bool):
            raise TypeError("allow_quit must be a boolean value.")
        if enabled and (pystray is None or Image is None or ImageDraw is None):
            raise RuntimeError(
                "System tray support requires pystray and Pillow. Install dependencies from requirements.txt."
            )

        self._system_tray_enabled = enabled
        self._system_tray_close_to_tray = close_to_tray
        self._system_tray_allow_restore = allow_restore
        self._system_tray_allow_quit = allow_quit
        self._system_tray_tooltip = tooltip or self.title
        self._system_tray_icon_path = self._normalize_optional_path(icon_path) if icon_path else None
        self._system_tray_menu_items = self._normalize_system_tray_menu_items(menu_items)

        if not enabled:
            self._is_in_system_tray = False
            self._stop_tray_icon()
            return

        self._ensure_tray_icon()

    def create_window(self) -> tk.Tk | tk.Toplevel:
        if self._is_top_level:
            if self._parent_root is None:
                raise RuntimeError("top_level windows require an existing parent window.")
            self.root = tk.Toplevel(self._parent_root)
        else:
            self.root = tk.Tk()
        self._apply_window_settings()

        try:
            self.browser = ConfigurableTkWebview(self.root, debug=self._debug_mode_enabled)
        except Exception as exc:
            if self.root is not None:
                self.root.destroy()
                self.root = None
            raise RuntimeError(
                "Failed to start WebView2. Make sure Microsoft Edge WebView2 Runtime is installed on Windows."
            ) from exc

        self.browser.pack(fill="both", expand=True)
        self._bind_window_events()
        self._register_pending_bindings()
        self._load_current_site()
        self._last_window_state = self._get_window_state()
        self._last_window_geometry = self._get_window_geometry()

        self.root.protocol("WM_DELETE_WINDOW", self._handle_close_request)
        self._emit_window_event("created")
        return self.root

    def top_level(
        self,
        site: str | None = None,
        window_size: tuple[int, int] | list[int] | None = None,
        title: str | None = None,
        **window_kwargs,
    ) -> "WebViewWindow":
        return self._create_child_window(
            site=site or self.site,
            window_size=window_size,
            title=title,
            **window_kwargs,
        )

    def topLevel(
        self,
        site: str | None = None,
        window_size: tuple[int, int] | list[int] | None = None,
        title: str | None = None,
        **window_kwargs,
    ) -> "WebViewWindow":
        return self.top_level(
            site=site,
            window_size=window_size,
            title=title,
            **window_kwargs,
        )

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
                    request_origin = meta.get("asset") or meta.get("href")
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

    def _handle_asset_navigation(self, target: str) -> bool:
        self.navigate(target)
        return True

    def _emit_to_frontend(self, name: str, *args) -> None:
        serialized_args = json.dumps(list(args), ensure_ascii=True)
        script = f"window.__webviewTkinterEmit('{name}', {serialized_args});"
        self.evaluate_js(script)

    def open_access_expose(
        self, allowed_sources: list[str] | tuple[str, ...] | set[str]
    ) -> None:
        self._open_access_expose_rules = self._normalize_access_sources(allowed_sources)

    def openAccessExpose(
        self, allowed_sources: list[str] | tuple[str, ...] | set[str]
    ) -> None:
        self.open_access_expose(allowed_sources)

    def open_access_site(
        self, allowed_sources: list[str] | tuple[str, ...] | set[str]
    ) -> None:
        normalized = self._normalize_access_sources(allowed_sources)
        normalized.add(self._home_site)
        self._open_access_site_rules = normalized
        self._install_bridge_script("site_access_guard", self._get_site_access_guard_script())

    def openAccessSite(
        self, allowed_sources: list[str] | tuple[str, ...] | set[str]
    ) -> None:
        self.open_access_site(allowed_sources)

    def lock(self, allowed_sources: list[str] | tuple[str, ...] | set[str]) -> None:
        self.open_access_expose(allowed_sources)

    def navigate(self, site: str) -> None:
        normalized_site = self._normalize_site(site)

        if self._open_access_site_rules and normalized_site not in self._open_access_site_rules:
            if self.browser is not None:
                self.site = self._home_site
                self._load_current_site()
            raise PermissionError(f"Site blocked by open_access_site(): {normalized_site}")

        self.site = normalized_site
        if self.browser is not None:
            self._load_current_site()

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
        if self._close_event_emitted:
            return

        self._close_event_emitted = True
        self._emit_window_event("closing")
        self._stop_tray_icon()
        self._is_in_system_tray = False

        for child_window in list(self._child_windows):
            child_window.close()
        self._child_windows.clear()

        if self.browser is not None:
            self.browser.destroy_webview()
            self.browser = None

        if self.root is not None:
            self.root.destroy()
            self.root = None

        self._emit_window_event("closed")

    def run(self) -> None:
        if self.root is None:
            self.create_window()

        if self.root is not None and not self._is_top_level:
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
