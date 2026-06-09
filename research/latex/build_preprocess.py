"""
Convert research/paper.md into LaTeX-ready pieces:
  - main.tex   (preamble + title + abstract + \input{body} + bibliography)
  - body.md    (processed markdown for pandoc -> body.tex)

Handles: [CITE: a; b] -> \cite{a,b} (and strips surrounding backticks); unicode symbols
mapped to LaTeX, separately for plain text (wrapped in $...$), math spans ($...$ / $$...$$,
bare commands), and inline code (ASCII fallback); a figure float injected at E11; manual
section numbers kept with secnumdepth=0 so prose cross-references stay consistent.
"""
import re, pathlib

src = pathlib.Path("research/paper.md").read_text()

# strip leading HTML comment
src = re.sub(r"^<!--.*?-->\s*", "", src, flags=re.S)

# title = first '# ' line
m = re.search(r"^# (.+)$", src, flags=re.M)
title = m.group(1).strip()

# abstract between '**Abstract.**' and '## 1. Introduction'
ab = re.search(r"\*\*Abstract\.\*\*(.+?)\n## 1\. Introduction", src, flags=re.S)
abstract = ab.group(1).strip()

# body from '## 1. Introduction' onward
body = src[src.index("## 1. Introduction"):]

# ----- citation conversion (strips optional surrounding backticks) -----
def cites(t):
    def repl(mm):
        keys = re.split(r"[;\s]+", mm.group(1).strip())
        keys = [k for k in keys if k]
        return "\\cite{" + ",".join(keys) + "}"
    return re.sub(r"`?\[CITE:\s*([^\]]+)\]`?", repl, t)

# ----- unicode maps -----
SUP = {"⁰":"0","¹":"1","²":"2","³":"3","⁴":"4","⁵":"5","⁶":"6","⁷":"7","⁸":"8","⁹":"9","⁻":"-","⁺":"+"}
SUPSET = "".join(SUP.keys())

BARE = {  # inside math: bare latex commands
 "α":"\\alpha","μ":"\\mu","ρ":"\\rho","σ":"\\sigma","θ":"\\theta","Σ":"\\Sigma","Δ":"\\Delta",
 "≤":"\\le","≥":"\\ge","×":"\\times","−":"-","·":"\\cdot","→":"\\to","∼":"\\sim","∈":"\\in",
 "√":"\\sqrt","⌊":"\\lfloor","⌋":"\\rfloor","𝟙":"\\mathbb{1}","∞":"\\infty","≈":"\\approx",
 "≠":"\\ne","Ŝ":"\\hat{S}","≅":"\\cong","∝":"\\propto","∀":"\\forall",
 "★":"\\star","±":"\\pm","…":"\\ldots","≡":"\\equiv",
}
WRAP = {  # plain text: mode-agnostic, passes through pandoc as raw LaTeX
 k: ("\\ensuremath{"+v+"}") for k, v in BARE.items()
}
ASCII = {  # inside code spans: plain ascii
 "α":"alpha","μ":"mu","ρ":"rho","σ":"sigma","θ":"theta","Σ":"Sum","Δ":"Delta","≤":"<=","≥":">=",
 "×":"x","−":"-","·":"*","→":"->","∼":"~","∈":" in ","√":"sqrt","⌊":"floor(","⌋":")",
 "𝟙":"1","∞":"inf","≈":"~=","≠":"!=","Ŝ":"S","∝":"prop","∀":"forall",
 "★":"*","±":"+/-","…":"...","≡":"==",
}

def map_sup(t, math=False):
    def repl(mm):
        s = "".join(SUP[c] for c in mm.group(0))
        return ("^{"+s+"}") if math else ("\\textsuperscript{"+s+"}")
    return re.sub("["+SUPSET+"]+", repl, t)

def apply_map(t, table):
    for k, v in table.items():
        t = t.replace(k, v)
    return t

def process(text):
    text = cites(text)
    store = {}
    i = [0]
    def stash(s):
        key = f"@@{i[0]}@@"; store[key] = s; i[0]+=1; return key
    # protect display math
    text = re.sub(r"\$\$(.+?)\$\$", lambda mm: stash(("dm", mm.group(1))), text, flags=re.S)
    # protect inline math (single $, not \$ , not $$)
    text = re.sub(r"(?<!\\)\$(?!\$)(.+?)(?<!\\)\$", lambda mm: stash(("im", mm.group(1))), text, flags=re.S)
    # protect inline code
    text = re.sub(r"`([^`]*)`", lambda mm: stash(("code", mm.group(1))), text)
    # plain text mapping
    text = apply_map(text, WRAP)
    text = map_sup(text, math=False)
    # restore
    for key, (kind, s) in store.items():
        if kind == "code":
            s2 = apply_map(s, ASCII); s2 = map_sup(s2, math=True)
            text = text.replace(key, "`"+s2+"`")
        else:
            s2 = apply_map(s, BARE); s2 = map_sup(s2, math=True)
            wrap = "$$" if kind == "dm" else "$"
            text = text.replace(key, wrap+s2+wrap)
    return text

abstract_t = process(abstract)
body_t = process(body)

# inject figure as a raw LaTeX float (controlled width; no height=\textheight so the caption
# does not collide with the page number) before E11's suite subsection (### 6.9)
fig = (
    "\n\n\\begin{figure}[htbp]\n\\centering\n"
    "\\includegraphics[width=0.92\\textwidth]{pstar_frontier.png}\n"
    "\\caption{The P\\ensuremath{\\star} frontier across target marginals. The exact-sum engine "
    "(solid) sits on the unconstrained same-family draw (dashed); enforcing the exact aggregate "
    "adds at most 0.006 in normalized 1-Wasserstein distance. The shaded gap to the target is "
    "shape-family mismatch.}\n\\label{fig:pstar}\n\\end{figure}\n\n")
body_t = body_t.replace("### 6.9 Suite-level", fig + "### 6.9 Suite-level", 1)

pathlib.Path("research/latex/body.md").write_text(body_t)

title_tex = title.replace("&", "\\&")
preamble = r"""\documentclass[11pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage[margin=1in]{geometry}
\usepackage{amsmath,amssymb}
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{array}
\usepackage{graphicx}
\usepackage{caption}
\usepackage{microtype}
\usepackage[numbers,sort&compress]{natbib}
\usepackage{etoolbox}
\AtBeginEnvironment{longtable}{\footnotesize}
\AtBeginEnvironment{tabular}{\footnotesize}
\setlength{\tabcolsep}{4pt}
\usepackage[hidelinks]{hyperref}
\setcounter{secnumdepth}{0}
\setlength{\parskip}{0.4em}
\setlength{\parindent}{0pt}
\setlength{\emergencystretch}{2em}
\title{__TITLE__}
\author{Muhammed Rasin\\ Independent Researcher\\ \texttt{rasinbinabdulla@gmail.com}}
\date{}
\begin{document}
\maketitle
\begin{abstract}
__ABSTRACT__
\end{abstract}
\input{body.tex}
\bibliographystyle{abbrvnat}
\bibliography{references}
\end{document}
"""
preamble = preamble.replace("__TITLE__", title_tex).replace("__ABSTRACT__", abstract_t)
pathlib.Path("research/latex/main.tex").write_text(preamble)
print("title:", title[:60])
print("abstract chars:", len(abstract_t), "| body chars:", len(body_t))
print("wrote research/latex/main.tex and body.md")
