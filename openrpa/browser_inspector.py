"""Visible, permission-gated browser inspection for authoring accessible activities."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from .network import assert_public_url

MAX_CONTROLS=300
MAX_TEXT=180


def build_control_descriptors(raw: list[dict[str,Any]]) -> list[dict[str,Any]]:
    """Convert a bounded DOM snapshot into normal Playwright activity selectors."""
    controls=[]
    for item in raw[:MAX_CONTROLS]:
        if not isinstance(item,dict): continue
        role=item.get("role") if isinstance(item.get("role"),str) else ""
        name=item.get("name") if isinstance(item.get("name"),str) else ""
        test_id=item.get("testId") if isinstance(item.get("testId"),str) else ""
        placeholder=item.get("placeholder") if isinstance(item.get("placeholder"),str) else ""
        tag=str(item.get("tag", "")).lower()[:20]
        input_type=str(item.get("inputType", "")).lower()[:20]
        if role and name:
            selector_kind,selector="role",f"{role}:{name}"
        elif test_id:
            selector_kind,selector="test_id",test_id
        elif placeholder:
            selector_kind,selector="placeholder",placeholder
        else:
            continue
        actions=[] if tag in {"input","textarea"} else ["read_text"]
        if role=="checkbox": actions.insert(0,"check");actions.insert(1,"uncheck")
        elif role=="radio": actions.insert(0,"check")
        elif role=="combobox" and tag=="select": actions.insert(0,"select")
        elif role in {"button","link","switch","menuitem","tab"} or tag in {"button","a"}:
            actions.insert(0,"click")
        if tag in {"input","textarea"} and input_type not in {"button","submit","reset","checkbox","radio","file","image"}:
            actions.insert(0,"fill")
        if not actions: continue
        try:match_count=int(item.get("matchCount",1))
        except (TypeError,ValueError):match_count=1
        controls.append({
            "selectorKind":selector_kind,"selector":selector,"role":role,"name":name,
            "tag":tag,"inputType":input_type,"placeholder":placeholder[:MAX_TEXT],
            "matchCount":max(0,min(match_count,10_000)),"actions":actions,
        })
    return controls


class BrowserInspector:
    """A single visible Playwright session owned by the local bridge process."""
    def __init__(self) -> None:
        self.runtime:Any=None
        self.browser:Any=None
        self.context:Any=None
        self.page:Any=None

    def open(self,url:str)->dict[str,Any]:
        if not isinstance(url,str) or not url.strip() or len(url)>2048:
            raise ValueError("Enter an HTTP(S) page URL of at most 2,048 characters")
        assert_public_url(url)
        self.close()
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError("Browser inspection requires the optional Playwright package and Chromium. See docs/AUTOMATION_ADAPTERS.md") from exc
        try:
            self.runtime=sync_playwright().start()
            self.browser=self.runtime.chromium.launch(headless=False)
            self.context=self.browser.new_context(service_workers="block",accept_downloads=False)
            self.page=self.context.new_page()
            self.page.set_default_timeout(10_000)
            self.page.set_default_navigation_timeout(20_000)
            def guard(route:Any)->None:
                try:
                    assert_public_url(route.request.url)
                    route.continue_()
                except Exception:
                    route.abort()
            self.context.route("**/*",guard)
            if hasattr(self.context,"route_web_socket"):
                self.context.route_web_socket("**/*",lambda websocket:websocket.close(code=1008,reason="Browser Inspector blocks WebSocket connections"))
            response=self.page.goto(url,wait_until="domcontentloaded",timeout=20_000)
            return {"url":self.page.url[:2048],"title":self.page.title()[:300],"status":response.status if response else None}
        except Exception:
            self.close()
            raise

    def controls(self)->dict[str,Any]:
        if self.page is None: raise RuntimeError("Open a page in the Browser Inspector first")
        raw=self.page.evaluate(_CONTROL_SNAPSHOT)
        if not isinstance(raw,list): raise RuntimeError("Browser returned an invalid control snapshot")
        controls=build_control_descriptors(raw)
        return {"url":self.page.url[:2048],"title":self.page.title()[:300],"controls":controls,"truncated":len(raw)>MAX_CONTROLS}

    def close(self)->None:
        if self.browser is not None:
            try:self.browser.close()
            except Exception:pass
        if self.runtime is not None:
            try:self.runtime.stop()
            except Exception:pass
        self.runtime=self.browser=self.context=self.page=None


_CONTROL_SNAPSHOT=r"""() => {
  const selector = 'button,a[href],input,textarea,select,[role],[contenteditable="true"]';
  const supportedRoles = new Set('alert alertdialog application article banner blockquote button caption cell checkbox code columnheader combobox complementary contentinfo definition deletion dialog directory document emphasis feed figure form grid gridcell group heading img insertion link list listbox listitem log main marquee math menu menubar menuitem menuitemcheckbox menuitemradio meter navigation note option paragraph progressbar radio radiogroup region row rowgroup rowheader scrollbar search searchbox separator slider spinbutton status strong subscript superscript switch tab table tablist tabpanel term textbox time timer toolbar tooltip tree treegrid treeitem'.split(' '));
  const roleFor = el => {
    const explicit = el.getAttribute('role'); if (explicit) return supportedRoles.has(explicit)?explicit:'';
    const tag = el.tagName.toLowerCase();
    if (tag === 'button') return 'button';
    if (tag === 'a' && el.hasAttribute('href')) return 'link';
    if (tag === 'textarea' || el.isContentEditable) return 'textbox';
    if (tag === 'select') return el.multiple ? 'listbox' : 'combobox';
    if (tag === 'input') {
      const type = (el.type || 'text').toLowerCase();
      if (type === 'checkbox') return 'checkbox'; if (type === 'radio') return 'radio';
      if (['button','submit','reset','image'].includes(type)) return 'button';
      if (type === 'search') return 'searchbox'; if (type === 'hidden' || type === 'file') return '';
      return 'textbox';
    }
    return '';
  };
  const labelFor = el => {
    const labelled = el.getAttribute('aria-labelledby');
    if (labelled) { const text = labelled.split(/\s+/).map(id => document.getElementById(id)?.innerText || '').join(' ').trim(); if (text) return text; }
    if (el.labels?.length) { const text = [...el.labels].map(label => label.innerText || '').join(' ').trim(); if (text) return text; }
    return '';
  };
  const candidates = [...document.querySelectorAll(selector)].filter(el => {
    const style = getComputedStyle(el), rect = el.getBoundingClientRect();
    return !!roleFor(el) && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
  });
  const entries = candidates.map(el => {
    const role = roleFor(el), tag = el.tagName.toLowerCase(), type = (el.type || '').toLowerCase();
    const labelled = labelFor(el);
    const name = (el.getAttribute('aria-label') || labelled || el.getAttribute('alt') || el.innerText || el.value || el.textContent || el.getAttribute('title') || '').trim().replace(/\s+/g, ' ').slice(0,180);
    const placeholder = (el.getAttribute('placeholder') || '').trim().slice(0,180);
    const testId = el.getAttribute('data-testid') || el.getAttribute('data-test-id') || '';
    return {role,name,placeholder,testId,tag,inputType:type};
  });
  const byRole = new Map(), byTestId = new Map(), byPlaceholder = new Map();
  for (const entry of entries) if (entry.role && entry.name) { const key = entry.role + '\0' + entry.name; byRole.set(key,(byRole.get(key)||0)+1); }
  for (const entry of entries) { if(entry.testId)byTestId.set(entry.testId,(byTestId.get(entry.testId)||0)+1); if(entry.placeholder)byPlaceholder.set(entry.placeholder,(byPlaceholder.get(entry.placeholder)||0)+1); }
  return entries.map(entry => ({...entry,matchCount:entry.role&&entry.name?(byRole.get(entry.role+'\0'+entry.name)||1):entry.testId?(byTestId.get(entry.testId)||1):entry.placeholder?(byPlaceholder.get(entry.placeholder)||1):1}));
}"""
