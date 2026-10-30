"""Browser engines with one constrained interface: goto, snapshot, fill, select, click, close.

The model never supplies JavaScript, selectors or URLs. It refers to elements by the ids in a snapshot,
and values come from task parameters. Every navigation is checked against the site policy.

* HttpEngine  — for Tandem's own simulated sites (plain HTML forms). Runs in-process through the Flask
  app (WSGI transport), so it works on serverless hosts and in tests.
* PlaywrightEngine — headless Chromium for real sites. Runs only in a browser worker (not on Vercel).
  No stealth plugins and no user-agent spoofing: if a site challenges automation, the run stops.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from urllib.parse import urlencode, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from flask import current_app

from app.services.browser.policy import check_navigation, is_sensitive_field
from app.services.browser.sites import Site

log = logging.getLogger("tandem.browser")
INTERNAL_BASE = "http://tandem.internal"


def playwright_available() -> bool:
    """Whether a browser worker (Playwright + Chromium) runs for this deployment. The web process only needs to
    know that; Playwright itself is imported by the worker that executes the job."""
    cfg = current_app.config
    return bool(cfg.get("BROWSER_WORKER_ENABLED")) and not cfg.get("ON_VERCEL")


@dataclass
class Snapshot:
    url: str
    title: str
    text: str
    elements: list[dict] = field(default_factory=list)
    html: str = ""
    frame_urls: list[str] = field(default_factory=list)

    def element(self, element_id: str) -> dict | None:
        return next((e for e in self.elements if e["id"] == element_id), None)

    def find(self, *, name: str | None = None, text: str | None = None, tag: str | None = None) -> dict | None:
        for e in self.elements:
            if name is not None and e.get("name") != name:
                continue
            if text is not None and text.lower() not in (e.get("text") or e.get("label") or "").lower():
                continue
            if tag is not None and e.get("tag") != tag:
                continue
            return e
        return None

    def for_model(self, limit: int = 120) -> str:
        """Compact, untrusted description of the page for the navigator model."""
        lines = [f"URL: {self.url}", f"Title: {self.title}", "Interactive elements:"]
        for e in self.elements[:limit]:
            bits = [e["id"], e["tag"]]
            for k in ("type", "name", "label", "placeholder", "text"):
                if e.get(k):
                    bits.append(f'{k}="{str(e[k])[:60]}"')
            if e.get("options"):
                bits.append("options=" + "|".join(o[:30] for o in e["options"][:15]))
            if e.get("sensitive"):
                bits.append("SENSITIVE(agent may not fill)")
            lines.append(" ".join(bits))
        lines.append("Visible text (excerpt):")
        lines.append(self.text[:2500])
        return "\n".join(lines)


class Engine:
    name = "base"

    def __init__(self, site: Site):
        self.site = site

    def goto(self, url: str) -> Snapshot: ...
    def snapshot(self) -> Snapshot: ...
    def fill(self, element_id: str, value: str) -> None: ...
    def select(self, element_id: str, option: str) -> None: ...
    def click(self, element_id: str) -> Snapshot: ...
    def screenshot(self) -> bytes | None: return None
    def close(self) -> None: ...
    def public_url(self, url: str) -> str: return url


class HttpEngine(Engine):
    """Form-level browser for Tandem's simulated sites, executed in-process through the Flask app."""

    name = "http"

    def __init__(self, site: Site):
        super().__init__(site)
        app = current_app._get_current_object()
        self.client = httpx.Client(transport=httpx.WSGITransport(app=app), base_url=INTERNAL_BASE,
                                   follow_redirects=False, timeout=20)
        self.current: Snapshot | None = None
        self.form_values: dict[int, dict[str, str]] = {}
        self._soup: BeautifulSoup | None = None

    def public_url(self, url: str) -> str:
        base = current_app.config.get("BACKEND_URL", "").rstrip("/")
        return base + urlparse(url).path + (("?" + urlparse(url).query) if urlparse(url).query else "")

    def _request(self, method: str, url: str, data: dict | None = None) -> Snapshot:
        for _ in range(5):
            absolute = urljoin(INTERNAL_BASE, url)
            check_navigation(self.site, absolute)
            if method == "GET":
                resp = self.client.get(absolute, params=data)
            else:
                resp = self.client.post(absolute, data=data)
            if resp.status_code in (301, 302, 303, 307, 308):
                url, method, data = resp.headers["location"], "GET", None
                continue
            self.current = self._parse(str(resp.url), resp.text)
            return self.current
        raise RuntimeError("Too many redirects")

    def _parse(self, url: str, html: str) -> Snapshot:
        soup = BeautifulSoup(html, "html.parser")
        self._soup = soup
        self.form_values = {}
        forms = soup.find_all("form")
        for i, form in enumerate(forms):
            values = {}
            for inp in form.find_all(["input", "select", "textarea"]):
                name = inp.get("name")
                if not name:
                    continue
                if inp.name == "select":
                    opt = inp.find("option", selected=True) or inp.find("option")
                    values[name] = (opt.get("value") or opt.get_text(strip=True)) if opt else ""
                elif inp.get("type") in ("submit", "button"):
                    continue
                else:
                    values[name] = inp.get("value", "")
            self.form_values[i] = values
        elements = []
        n = 0
        for node in soup.find_all(["a", "input", "select", "textarea", "button"]):
            if node.name == "input" and node.get("type") == "hidden":
                continue
            n += 1
            form = node.find_parent("form")
            label = ""
            if node.get("id"):
                lab = soup.find("label", attrs={"for": node.get("id")})
                label = lab.get_text(" ", strip=True) if lab else ""
            if not label and node.find_parent("label"):
                label = node.find_parent("label").get_text(" ", strip=True)
            el = {
                "id": f"e{n}", "tag": node.name, "type": node.get("type", "") if node.name != "a" else "link",
                "name": node.get("name", ""), "id_attr": node.get("id", ""), "label": label,
                "placeholder": node.get("placeholder", ""), "autocomplete": node.get("autocomplete", ""),
                "text": node.get_text(" ", strip=True)[:120] if node.name in ("a", "button") else (node.get("value", "") if node.get("type") == "submit" else ""),
                "href": node.get("href", ""), "form": forms.index(form) if form else None,
                "data": {k[5:]: v for k, v in node.attrs.items() if k.startswith("data-")},
            }
            if node.name == "select":
                el["options"] = [o.get_text(strip=True) for o in node.find_all("option")]
                el["option_values"] = [o.get("value", o.get_text(strip=True)) for o in node.find_all("option")]
            el["sensitive"] = is_sensitive_field(el)
            node["data-tandem-id"] = el["id"]
            elements.append(el)
        title = soup.title.get_text(strip=True) if soup.title else ""
        text = soup.get_text(" ", strip=True)
        return Snapshot(url=url, title=title, text=text, elements=elements, html=html)

    def goto(self, url: str) -> Snapshot:
        return self._request("GET", url)

    def snapshot(self) -> Snapshot:
        assert self.current is not None
        return self.current

    def _el(self, element_id: str) -> dict:
        el = self.snapshot().element(element_id)
        if el is None:
            raise ValueError(f"No element {element_id} on the page")
        return el

    def fill(self, element_id: str, value: str) -> None:
        el = self._el(element_id)
        if el.get("sensitive"):
            from app.services.browser.policy import PolicyViolation

            raise PolicyViolation("The agent never fills password, payment or identity-document fields", "sensitive_field")
        if el["form"] is None or not el["name"]:
            raise ValueError("Element is not a form field")
        self.form_values[el["form"]][el["name"]] = value

    def select(self, element_id: str, option: str) -> None:
        el = self._el(element_id)
        labels, values = el.get("options", []), el.get("option_values", [])
        if option in values:
            chosen = option
        elif option in labels:
            chosen = values[labels.index(option)]
        else:
            raise ValueError(f"'{option}' is not an option of {element_id}")
        self.form_values[el["form"]][el["name"]] = chosen

    def click(self, element_id: str) -> Snapshot:
        el = self._el(element_id)
        if el["tag"] == "a" and el.get("href"):
            return self._request("GET", urljoin(self.snapshot().url, el["href"]))
        if el["form"] is None:
            raise ValueError("Element does not submit anything")
        form = self._soup.find_all("form")[el["form"]]
        values = dict(self.form_values[el["form"]])
        for hidden in form.find_all("input", type="hidden"):
            if hidden.get("name"):
                values.setdefault(hidden["name"], hidden.get("value", ""))
        if el.get("name"):
            node = self._soup.find(attrs={"data-tandem-id": element_id})
            values[el["name"]] = node.get("value", "") if node is not None else ""
        action = urljoin(self.snapshot().url, form.get("action") or self.snapshot().url)
        method = (form.get("method") or "GET").upper()
        if method == "GET":
            return self._request("GET", action.split("?")[0] + "?" + urlencode(values))
        return self._request("POST", action, data=values)

    def close(self) -> None:
        self.client.close()


_SNAPSHOT_JS = r"""
() => {
  const visible = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const labelOf = el => {
    if (el.labels && el.labels.length) return el.labels[0].innerText.trim();
    return (el.getAttribute('aria-label') || el.getAttribute('title') || '').trim();
  };
  const nodes = Array.from(document.querySelectorAll('a[href], input, select, textarea, button, [role=button], [role=option], [role=link]'));
  let n = 0; const out = [];
  for (const el of nodes) {
    if (!visible(el) || (el.tagName === 'INPUT' && el.type === 'hidden')) continue;
    n += 1; const id = 'e' + n; el.setAttribute('data-tandem-id', id);
    out.push({ id, tag: el.tagName.toLowerCase(), type: (el.type || el.getAttribute('role') || '').toLowerCase(),
      name: el.name || '', id_attr: el.id || '', label: labelOf(el), placeholder: el.placeholder || '',
      autocomplete: el.autocomplete || '', text: (el.innerText || el.value || '').trim().slice(0, 120),
      href: el.getAttribute('href') || '',
      options: el.tagName === 'SELECT' ? Array.from(el.options).map(o => o.text.trim()) : undefined });
    if (out.length >= 250) break;
  }
  return { title: document.title, text: (document.body ? document.body.innerText : '').slice(0, 6000), elements: out };
}
"""


class PlaywrightEngine(Engine):
    name = "playwright"

    def __init__(self, site: Site):
        super().__init__(site)
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        cdp = current_app.config.get("BROWSER_CDP_URL")
        if cdp:
            self.browser = self._pw.chromium.connect_over_cdp(cdp)
        else:
            self.browser = self._pw.chromium.launch(headless=True)
        self.context = self.browser.new_context(viewport={"width": 1280, "height": 900}, locale="en-GB")
        self.page = self.context.new_page()
        self.page.set_default_timeout(20000)
        self.current: Snapshot | None = None

    def _check_current(self) -> None:
        check_navigation(self.site, self.page.url)

    def snapshot(self) -> Snapshot:
        data = self.page.evaluate(_SNAPSHOT_JS)
        elements = data["elements"]
        for e in elements:
            e["sensitive"] = is_sensitive_field(e)
        self.current = Snapshot(url=self.page.url, title=data["title"], text=data["text"], elements=elements,
                                html=self.page.content(), frame_urls=[f.url for f in self.page.frames])
        return self.current

    def goto(self, url: str) -> Snapshot:
        check_navigation(self.site, url)
        self.page.goto(url, wait_until="domcontentloaded")
        self.page.wait_for_timeout(1200)
        self._check_current()
        return self.snapshot()

    def _locator(self, element_id: str):
        return self.page.locator(f'[data-tandem-id="{element_id}"]').first

    def fill(self, element_id: str, value: str) -> None:
        el = self.current.element(element_id) if self.current else None
        if el is None:
            raise ValueError(f"No element {element_id} on the page")
        if el.get("sensitive"):
            from app.services.browser.policy import PolicyViolation

            raise PolicyViolation("The agent never fills password, payment or identity-document fields", "sensitive_field")
        self._locator(element_id).fill(value)

    def select(self, element_id: str, option: str) -> None:
        self._locator(element_id).select_option(label=option)

    def click(self, element_id: str) -> Snapshot:
        self._locator(element_id).click()
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:  # noqa: BLE001 - single-page apps may not navigate
            pass
        self.page.wait_for_timeout(1500)
        self._check_current()
        return self.snapshot()

    def screenshot(self) -> bytes | None:
        masks = [self._locator(e["id"]) for e in (self.current.elements if self.current else []) if e.get("sensitive")]
        return self.page.screenshot(type="jpeg", quality=60, mask=masks, full_page=False)

    def close(self) -> None:
        for closer in (self.context.close, self.browser.close, self._pw.stop):
            try:
                closer()
            except Exception:  # noqa: BLE001
                pass
