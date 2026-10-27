#!/usr/bin/env python3
"""
WhyLine — The Agent That Can Explain Why
=========================================
An evidence-first research agent. Given a complex question, it:
  1. DECOMPOSES the question into the sub-facts needed to answer it
  2. SEARCHES four independent data sources in parallel
  3. CROSS-VALIDATES findings across sources (agreement / conflict flags)
  4. SYNTHESIZES an evidence-backed answer with a visible WHY-chain
  5. SCORES confidence from cross-source corroboration, not vibes

Reasoning layer: NVIDIA Nemotron (https://build.nvidia.com) via NVIDIA_API_KEY.
Without a key the agent runs in Deterministic Mode (extractive synthesis),
so the pipeline is fully functional without any paid service.

Open Agent Hackathon 2026 — Track 02: The Agent That Can Explain Why.
Team: Shimi Studio Agents
"""
import argparse, base64, concurrent.futures, datetime, html, json, os, re, sys, time
import urllib.parse, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"}
SOURCES = []

def source(name):
    def deco(fn):
        SOURCES.append((name, fn)); return fn
    return deco

def _get(url, timeout=15, retries=2):
    """GET with polite backoff for rate-limited sources (429/503)."""
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 503) and attempt < retries:
                time.sleep(2.5 * (attempt + 1)); continue
            raise
    raise last

def _strip(t):
    t = re.sub(r"<[^>]+>", " ", t or "")
    return html.unescape(re.sub(r"\s+", " ", t)).strip()

@source("Wikipedia")
def src_wikipedia(q):
    """Encyclopedic facts — high-authority baseline. One API call, snippets included."""
    api = ("https://en.wikipedia.org/w/api.php?action=query&list=search&format=json"
           "&srlimit=4&srsearch=" + urllib.parse.quote(q))
    hits = json.loads(_get(api))["query"]["search"]
    return [{"title": h["title"], "text": _strip(h["snippet"])[:400],
             "url": "https://en.wikipedia.org/wiki/" + h["title"].replace(" ", "_")}
            for h in hits]

@source("Bing")
def _parse_bing(raw):
    items = re.findall(r'<li class="b_algo".*?<h2[^>]*><a[^>]+href="([^"]+)"[^>]*>(.*?)</a></h2>', raw, re.S)
    snips = re.findall(r'<p class="b_lineclamp[^"]*"[^>]*>(.*?)</p>', raw, re.S)
    def realurl(u):
        m = re.search(r'u=a1([^&]+)', html.unescape(u))
        if not m:
            return u
        b = m.group(1); b += "=" * (-len(b) % 4)
        try:
            return base64.urlsafe_b64decode(b).decode("utf-8", "ignore")
        except Exception:
            return u
    out = []
    for i, (u, t) in enumerate(items[:6]):
        snip = _strip(snips[i])[:400] if i < len(snips) else ""
        out.append({"title": _strip(t)[:120], "text": snip, "url": realurl(u)})
    return out

def src_bing(q):
    """Open web search — breadth of coverage. Junk-filtered with one retry."""
    out = _parse_bing(_get("https://www.bing.com/search?count=10&q=" + urllib.parse.quote(q)))
    qkws = set(keywords(q, 5))
    def relevant(rs):
        return any(set(keywords(r["title"], 8)) & qkws for r in rs) if rs else False
    if not relevant(out):
        time.sleep(1.2)
        retry = _parse_bing(_get("https://www.bing.com/search?count=10&q=" + urllib.parse.quote(q)))
        if relevant(retry):
            return retry
        return []  # serve nothing rather than garbage
    return out
    items = re.findall(r'<li class="b_algo".*?<h2[^>]*><a[^>]+href="([^"]+)"[^>]*>(.*?)</a></h2>', raw, re.S)
    snips = re.findall(r'<p class="b_lineclamp[^"]*"[^>]*>(.*?)</p>', raw, re.S)
    def realurl(u):
        m = re.search(r'u=a1([^&]+)', html.unescape(u))
        if not m:
            return u
        b = m.group(1); b += "=" * (-len(b) % 4)
        try:
            return base64.urlsafe_b64decode(b).decode("utf-8", "ignore")
        except Exception:
            return u
    out = []
    for i, (u, t) in enumerate(items[:6]):
        snip = _strip(snips[i])[:400] if i < len(snips) else ""
        out.append({"title": _strip(t)[:120], "text": snip, "url": realurl(u)})
    return out

@source("Crossref")
def src_crossref(q):
    """Academic literature — peer-reviewed evidence layer."""
    data = json.loads(_get("https://api.crossref.org/works?rows=5&select=title,abstract,URL,DOI&query="
                           + urllib.parse.quote(q)))
    out = []
    for it in data["message"]["items"]:
        title = (it.get("title") or ["Untitled"])[0][:160]
        abstract = _strip(re.sub(r"<[^>]+>", " ", it.get("abstract") or ""))[:400]
        out.append({"title": title, "text": abstract, "url": it.get("URL") or ("https://doi.org/" + it["DOI"])})
    return out

@source("News")
def src_news(q):
    """News media (Google News RSS) — recent developments and reporting."""
    raw = _get("https://news.google.com/rss/search?q=" + urllib.parse.quote(q)
               + "&hl=en-US&gl=US&ceid=US:en")
    items = re.findall(r"<item>(.*?)</item>", raw, re.S)[:5]
    out = []
    for it in items:
        t = re.search(r"<title>(.*?)</title>", it, re.S)
        l = re.search(r"<link>(.*?)</link>", it, re.S)
        pub = re.search(r"<pubDate>(.*?)</pubDate>", it, re.S)
        title = _strip(t.group(1)) if t else ""
        # google news titles end with " - Publisher"
        m = re.match(r"(.*)\s+-\s+([^-]+)$", title)
        text = (f"[{m.group(2)}] " if m else "") + (pub.group(1)[:22] if pub else "")
        out.append({"title": title[:140], "text": text, "url": l.group(1) if l else ""})
    return out

@source("Marginalia")
def src_marginalia(q):
    """Independent non-commercial index — the long tail of the web."""
    raw = _get("https://search.marginalia.nu/search?query=" + urllib.parse.quote(q))
    links = re.findall(r'<a[^>]+href="(https?://(?!search\.marginalia)[^"]+)"[^>]*>(.*?)</a>', raw, re.S)
    out, seen = [], set()
    for u, t in links:
        if u in seen:
            continue
        seen.add(u)
        out.append({"title": _strip(t)[:120] or u[:90], "text": "", "url": u})
        if len(out) >= 5:
            break
    return out

# ------------------------------------------------------------------ llm layer
class Nemotron:
    """NVIDIA Nemotron reasoning layer. Set NVIDIA_API_KEY to enable.
    Endpoint: integrate.api.nvidia.com (OpenAI-compatible)."""
    def __init__(self):
        self.key = os.environ.get("NVIDIA_API_KEY", "")
        self.model = os.environ.get("NVIDIA_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b")
        self.url = "https://integrate.api.nvidia.com/v1/chat/completions"

    @property
    def active(self):
        return bool(self.key)

    def ask(self, system, user, max_tokens=700):
        if not self.active:
            return None
        body = json.dumps({"model": self.model, "max_tokens": max_tokens, "temperature": 0.2,
                           "messages": [{"role": "system", "content": system},
                                        {"role": "user", "content": user}]}).encode()
        req = urllib.request.Request(self.url, data=body, method="POST", headers={
            "Authorization": "Bearer " + self.key, "Content-Type": "application/json", **UA})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())["choices"][0]["message"]["content"]
        except Exception:
            return None

# ------------------------------------------------------------ question pipeline
QUESTION_KWS = set()
STOP = set("the a an of for to in on and or is are was were with by from as at that this it its "
           "their about into over under across why how what when who does do did more most than "
           "between among can could should would will".split())

def keywords(text, n=8):
    words = re.findall(r"[A-Za-z][A-Za-z\-]{2,}", text.lower())
    return [w for w in dict.fromkeys(words) if w not in STOP][:n]

def entities(text):
    """Extract capitalized entity spans — the searchable core of a question."""
    spans = re.findall(r"(?:[A-Z][a-z]+|\b[A-Z]{2,6}\b)(?:\s+(?:[A-Z][a-z]+|\b[A-Z]{2,6}\b))*", text)
    spans = [s for s in spans if s.lower() not in STOP and len(s) > 2]
    seen, out = set(), []
    for s in spans:
        if s not in seen:
            seen.add(s); out.append(s)
    return out[:4]

def search_query(question, tail):
    """Build a short, entity-focused query: entities + non-entity keywords."""
    ents = entities(question)
    head = " ".join(ents[:2])
    kws = [k for k in keywords(question, 5) if k not in head.lower()][:3]
    q = f"{head} {' '.join(kws)}".strip()
    return q or tail

def decompose(question, llm):
    """Sub-question generation. Nemotron when available; heuristic fallback."""
    out = llm.ask("You decompose a complex research question into 3-5 concrete, searchable "
                  "sub-questions. Return ONLY a JSON array of strings, each under 12 words.",
                  question)
    if out:
        try:
            arr = json.loads(re.search(r"\[.*\]", out, re.S).group(0))
            if isinstance(arr, list) and arr:
                return [str(s)[:140] for s in arr][:5]
        except Exception:
            pass
    ents = entities(question)
    head = " ".join(ents[:2]) if ents else " ".join(keywords(question, 3))
    kws = [k for k in keywords(question, 5) if k not in head.lower()][:3]
    return [f"{head} overview",
            f"{head} {' '.join(kws[:2])} explained",
            f"{head} criticism and risks"]

SHORT_Q = {"Wikipedia":  lambda q: search_query(q, q)[:60],
           "Bing":      lambda q: search_query(q, q)[:70],
           "Crossref":  lambda q: search_query(q, q)[:70],
           "News":      lambda q: search_query(q, q)[:60],
           "Marginalia": lambda q: search_query(q, q)[:50]}

def harvest(question):
    """Fan-out search across all four sources, in parallel, each with a tailored query.
    Relevance-gated: a finding must share at least one keyword with the question."""
    qkws = set(keywords(question, 10)) | set(w.lower() for w in entities(question))
    found = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(fn, SHORT_Q[name](question)): name for name, fn in SOURCES}
        for f in concurrent.futures.as_completed(futs):
            try:
                found += [{"_src": futs[f], **r} for r in (f.result() or [])]
            except Exception:
                pass
    seen, clean = set(), []
    for r in found:
        if r["url"] in seen or "marginalia.nu" in r["url"]:
            continue
        item_kws = set(keywords(r["title"] + " " + r.get("text", ""), 14))
        if qkws and not (item_kws & qkws):
            continue  # junk-gate
        seen.add(r["url"]); clean.append(r)
    return clean

def _bag(text, n=10):
    return set(keywords(text, n))

def cross_validate(findings):
    """Cluster findings into claims by word-overlap (Jaccard), then measure
    how many INDEPENDENT sources support each claim."""
    claims = []  # each: {bag, items}
    for f in findings:
        bag = _bag((f["title"] + " " + f["text"])[:400], 12)
        if not bag:
            bag = {f["_src"]}
        placed = False
        for c in claims:
            inter = bag & c["bag"]
            union = len(bag | c["bag"]) or 1
            key_inter = len(inter & QUESTION_KWS)
            if (key_inter >= 2) or (len(inter) / union >= 0.30) or (len(inter) >= 4):
                c["bag"] |= bag; c["items"].append(f); placed = True
                break
        if not placed:
            claims.append({"bag": bag, "items": [f]})
    matrix = []
    for c in claims:
        srcs = sorted({g["_src"] for g in c["items"]})
        titles = [g["title"] for g in c["items"]]
        # claim label = longest common-ish title
        label = max(titles, key=len)[:110]
        matrix.append({"claim": label, "sources": srcs, "support": len(srcs),
                       "n_items": len(c["items"]),
                       "urls": [g["url"] for g in c["items"]][:3],
                       "status": "corroborated" if len(srcs) > 1 else "single-source"})
    matrix.sort(key=lambda m: (-m["support"], -m["n_items"]))
    return matrix

def synthesize(question, findings, matrix, llm):
    """Evidence-backed answer + WHY-chain. Nemotron when available; extractive fallback."""
    evidence = "\n".join(f"[{f['_src']}] {f['title']} :: {f['text'][:220]} ({f['url']})"
                         for f in findings[:14])
    out = llm.ask(
        "You are an evidence-first analyst. Answer using ONLY the evidence provided. "
        "Structure exactly: ANSWER: (3-6 sentences) / WHY-CHAIN: (one bullet per reasoning "
        "step: sub-finding -> conclusion) / CONTRADICTIONS: (or 'none found') / CONFIDENCE: "
        "(0-100 with a one-line justification).",
        f"QUESTION: {question}\n\nEVIDENCE:\n{evidence}")
    if out:
        return {"mode": "nemotron-synthesis", "answer": out}
    top = matrix[:4]
    chain = [f"{m['status'].upper()}: {m['claim']}  (sources: {', '.join(m['sources'])})"
              for m in top]
    corr = sum(m["support"] for m in top if m["status"] == "corroborated")
    conf = min(92, 35 + corr * 15 + (8 if len(findings) > 10 else 0))
    return {"mode": "deterministic-extractive", "answer":
            f"Findings: {len(findings)} items from "
            f"{len({f['_src'] for f in findings})} independent sources.\n\n"
            "WHY-CHAIN:\n" + "\n".join(chain)
            + f"\n\nCONTRADICTIONS: {sum(1 for m in matrix if m['status']=='single-source')} "
              "claims remain single-source (unverified).\n"
            f"CONFIDENCE: {conf}/100 — derived from cross-source corroboration, not self-report.",
            "why_chain": chain, "confidence": conf}

# --------------------------------------------------------------------- runner
def run(question, verbose=True):
    global QUESTION_KWS
    QUESTION_KWS = set(keywords(question, 10)) | set(w.lower() for w in entities(question))
    t0 = time.time()
    llm = Nemotron()
    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    log("")
    log("WHY-LINE AGENT")
    log("=" * 72)
    log(f"QUESTION: {question}")
    log(f"[1/4] reasoning engine: "
        f"{'NVIDIA Nemotron (' + llm.model + ')' if llm.active else 'deterministic mode'}")

    subs = decompose(question, llm)
    log(f"[1/4] decomposed into {len(subs)} sub-questions:")
    for s in subs:
        log("      - " + s)

    log(f"[2/4] harvesting {len(SOURCES)} independent sources per sub-question ...")
    findings = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        for res in ex.map(harvest, subs):
            findings += res
    seen, uniq = set(), []
    for f in findings:
        if f["url"] not in seen:
            seen.add(f["url"]); uniq.append(f)
    findings = uniq
    srcs = sorted({f["_src"] for f in findings})
    log(f"[2/4] {len(findings)} unique evidence items from {len(srcs)} sources: {', '.join(srcs)}")

    log("[3/4] cross-validating claims across sources ...")
    matrix = cross_validate(findings)
    corr = [m for m in matrix if m["status"] == "corroborated"]
    log(f"[3/4] {len(corr)}/{len(matrix)} claims corroborated by 2+ independent sources")

    log("[4/4] synthesizing evidence-backed answer ...")
    synth = synthesize(question, findings, matrix, llm)
    dt = time.time() - t0
    log(f"[4/4] done in {dt:.1f}s — synthesis mode: {synth['mode']}")
    log("=" * 72)
    log(synth["answer"])
    log("=" * 72)
    return {"question": question, "sub_questions": subs, "findings": findings,
            "matrix": matrix, "synthesis": synth, "seconds": round(dt, 1),
            "engine": "nemotron" if llm.active else "deterministic",
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat()}

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="WhyLine — the agent that can explain why")
    ap.add_argument("question")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--json-out")
    a = ap.parse_args()
    r = run(a.question, verbose=not a.quiet)
    if a.json_out:
        with open(a.json_out, "w", encoding="utf-8") as fh:
            json.dump(r, fh, indent=1, ensure_ascii=False)
