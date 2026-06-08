#!/usr/bin/env python3
"""Generate a self-contained literature-explorer HTML page from a data JSON.

Reuses the shell (CSS + renderer JS) of an existing explorer and swaps in
topic-specific strings + the embedded `data` JSON, so every explorer in this
repo is visually and behaviourally identical.

Usage:
  python gen_lit_explorer.py --data data/multiagent_orchestration.json \
      --out explorers/multiagent-orchestration.html

Data JSON schema (see data/*.json):
  meta: {title, h1, sub, tkey, what_is, caveat?, start_here:[], one_paragraph?,
         podcast?, note_r_label?, measured_label?, design_label?, design_sub?}
  branch_labels: {key: label}
  papers: [{bibcode,title,first_author,year,citation_count,arxiv?,branches:[key],
            notes:[{branch,k,r}], reading_rank?}]
  sections: [{key,label,subtopic,themes:[],how_measured:[],gaps:[],notable:[],papers:[bibcode]}]
  reading: [[bibcode,title,group], ...]
  opportunities: [[title,desc], ...]
  design: [{title,bibcode,task_design,data_generation,metrics,key_numbers:[],reusable_for_role}]
  design_principles: [], design_pitfalls: []
  temporal: {publication_volume:[{year,count,note?}],
             citation_trajectories:[{bibcode,title,per_year:[{year,citations}]}],
             benchmark_progression:[], narrative}
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SHELL_DEFAULT = str(Path(__file__).parent / "_shell.html")

GENERIC_HOME = """function homeHTML(){
  const m=D.meta||{};
  const stats=`${D.papers.length} papers \\u00b7 ${D.sections.length} themes`+(D.reading&&D.reading.length?` \\u00b7 ${D.reading.length}-paper reading path`:'');
  let h=`<h2 class="sectionhead">Overview</h2><p class="subtopic">${esc(stats)}</p>`;
  if(m.what_is){h+=`<div class="panel"><h3>What this is</h3><p class="val">${m.what_is}</p>`+(m.caveat?`<p class="hint">${m.caveat}</p>`:'')+`</div>`;}
  if(m.start_here&&m.start_here.length){h+=`<div class="panel"><h3>Start here</h3><ul style="margin:0;padding-left:18px">`+m.start_here.map(s=>`<li style=\\"margin-bottom:6px\\">${s}</li>`).join('')+`</ul></div>`;}
  if(m.one_paragraph){h+=`<div class="panel themes"><h3>The field in one paragraph</h3><p class="val">${m.one_paragraph}</p></div>`;}
  if(m.podcast){h+=`<div class="panel measured"><h3>Companion podcast</h3><p class="val">${m.podcast}</p></div>`;}
  return h;
}
"""


def derive_arxiv(bibcode: str) -> str | None:
    # 2024arXiv240201680G -> 2402.01680 ; only for arXiv bibcodes
    m = re.match(r"^\d{4}arXiv(\d{4})(\d{5})[A-Za-z]$", bibcode)
    if m:
        return f"{m.group(1)}.{m.group(2)}"
    return None


def build(shell: str, data: dict) -> str:
    meta = data.get("meta", {})
    for p in data.get("papers", []):
        if not p.get("arxiv"):
            ax = derive_arxiv(p.get("bibcode", ""))
            if ax:
                p["arxiv"] = ax

    html = shell
    html = re.sub(r"<title>.*?</title>",
                  f"<title>{meta['title']} &middot; Literature Explorer</title>", html, flags=re.S)
    html = re.sub(r"<h1>.*?</h1>", f"<h1>{meta['h1']}</h1>", html, count=1, flags=re.S)
    html = re.sub(r'<div class="sub">.*?</div>',
                  f'<div class="sub">{meta["sub"]}</div>', html, count=1, flags=re.S)
    html = html.replace("const TKEY='amm-theme';", f"const TKEY='{meta.get('tkey','litx')}';")

    # generalize hardcoded role/forgetting strings
    html = html.replace("why it matters for the role", meta.get("note_r_label", "why it matters"))
    html = html.replace("'How forgetting is measured (or not)'",
                        json.dumps(meta.get("measured_label", "Evidence & metrics")))
    html = html.replace("Reusable for the role", meta.get("design_label", "Reusable in practice"))
    html = html.replace("Thirteen papers to get current fast, grouped by role.",
                        "${D.reading.length} papers to get current fast.")
    html = html.replace("White-space mapped to the role, ranked by leverage.",
                        "Open problems and white space, ranked by leverage.")
    html = html.replace(
        "Full-text extraction of the three keystone papers: exact task schemas, data-generation recipes, and metrics a harness-builder can reuse.",
        meta.get("design_sub", "Deep dives into keystone papers: methods, evidence, and what is reusable."))

    # swap homeHTML() for the generic, meta-driven version
    a = html.index("function homeHTML(){")
    b = html.index("function readingHTML(){")
    html = html[:a] + GENERIC_HOME + html[b:]

    # inject data
    open_tag = '<script id="data" type="application/json">'
    s = html.index(open_tag) + len(open_tag)
    e = html.index("</script>", s)
    html = html[:s] + json.dumps(data, ensure_ascii=False) + html[e:]
    return html


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--shell", default=SHELL_DEFAULT)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    shell = Path(args.shell).read_text()
    data = json.loads(Path(args.data).read_text())
    out = build(shell, data)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(out)
    print(f"wrote {args.out} ({len(out)} bytes, {len(data.get('papers', []))} papers)")


if __name__ == "__main__":
    main()
