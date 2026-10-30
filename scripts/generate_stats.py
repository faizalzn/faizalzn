#!/usr/bin/env python3
"""Membuat kartu statistik GitHub sebagai file SVG (tanpa layanan pihak ketiga).

Keluaran (folder assets/):
  stats.svg          kartu statistik + peringkat
  languages.svg      bahasa paling banyak dipakai (repo publik, bukan fork)
  lang-repo.svg      donat: bahasa utama per repositori
  lang-commit.svg    donat: bahasa utama per commit (12 bulan terakhir)
  activity-year.svg  grafik kontribusi 12 bulan terakhir (per minggu)
  activity-30d.svg   grafik aktivitas 30 hari terakhir (per hari)

Pemakaian:
  GITHUB_TOKEN=... GH_USER=username python scripts/generate_stats.py
  python scripts/generate_stats.py --placeholder     # kartu "menunggu update pertama"

Hanya memakai pustaka standar Python.
"""
import datetime as dt
import html
import json
import math
import os
import sys
import urllib.request

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")

BG, BORDER = "#0d1117", "#2a3558"
TITLE, TEXT, MUTED = "#22d3ee", "#E6EDF3", "#8b98b8"
ACCENT, ACCENT2 = "#ff6ec7", "#7ee7d0"
FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Arial, sans-serif"

QUERY = """
query($login:String!){
  user(login:$login){
    name login
    followers{ totalCount }
    repositories(first:100, ownerAffiliations:OWNER, isFork:false, privacy:PUBLIC){
      totalCount
      nodes{
        stargazerCount forkCount
        primaryLanguage{ name color }
        languages(first:10, orderBy:{field:SIZE, direction:DESC}){
          edges{ size node{ name color } }
        }
      }
    }
    pullRequests{ totalCount }
    issues{ totalCount }
    contributionsCollection{
      totalCommitContributions
      restrictedContributionsCount
      commitContributionsByRepository(maxRepositories:100){
        repository{ primaryLanguage{ name color } }
        contributions{ totalCount }
      }
      contributionCalendar{
        totalContributions
        weeks{ contributionDays{ date contributionCount } }
      }
    }
  }
}
"""


# ----------------------------------------------------------------- data ----
def fetch(login, token):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json",
                 "User-Agent": "profile-stats-generator"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        payload = json.load(r)
    if payload.get("errors") or not (payload.get("data") or {}).get("user"):
        raise SystemExit(f"GraphQL error: {payload.get('errors') or 'user tidak ditemukan'}")
    return payload["data"]["user"]


def summarize(user):
    repos = user["repositories"]["nodes"]
    langs = {}
    for repo in repos:
        for edge in repo["languages"]["edges"]:
            n = edge["node"]
            item = langs.setdefault(n["name"], {"size": 0, "color": n["color"] or "#8b98b8"})
            item["size"] += edge["size"]
    cc = user["contributionsCollection"]
    days = [d for w in cc["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    # donat: jumlah repositori per bahasa utama, dan jumlah commit (12 bln) per bahasa utama repo
    repo_langs, commit_langs = {}, {}
    for repo in repos:
        pl = repo.get("primaryLanguage")
        if pl:
            item = repo_langs.setdefault(pl["name"], {"size": 0, "color": pl["color"] or "#8b98b8"})
            item["size"] += 1
    for entry in cc["commitContributionsByRepository"]:
        pl = entry["repository"].get("primaryLanguage")
        if pl:
            item = commit_langs.setdefault(pl["name"], {"size": 0, "color": pl["color"] or "#8b98b8"})
            item["size"] += entry["contributions"]["totalCount"]
    return {
        "repo_langs": repo_langs,
        "commit_langs": commit_langs,
        "name": user["name"] or user["login"],
        "stars": sum(r["stargazerCount"] for r in repos),
        "forks": sum(r["forkCount"] for r in repos),
        "repos": user["repositories"]["totalCount"],
        "followers": user["followers"]["totalCount"],
        "prs": user["pullRequests"]["totalCount"],
        "issues": user["issues"]["totalCount"],
        "commits": cc["totalCommitContributions"] + cc["restrictedContributionsCount"],
        "contribs": cc["contributionCalendar"]["totalContributions"],
        "langs": langs,
        "days": [(dt.date.fromisoformat(d["date"]), d["contributionCount"]) for d in days],
    }


def grade(s):
    score = (s["commits"] * 1.0 + s["prs"] * 3 + s["issues"] * 1.5
             + s["stars"] * 2 + s["followers"] * 1.5 + s["repos"] * 0.5)
    for limit, g in ((1500, "S"), (700, "A+"), (350, "A"), (150, "B+"), (60, "B"), (20, "C+")):
        if score >= limit:
            return g, min(1.0, score / 1500)
    return "C", min(1.0, max(score, 3) / 1500)


# ------------------------------------------------------------------ svg ----
def esc(t):
    return html.escape(str(t), quote=True)


def card(w, h, body, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'role="img" aria-label="{esc(title)}">'
            f'<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="10" fill="{BG}" stroke="{BORDER}"/>'
            f'<text x="24" y="34" font-family="{FONT}" font-size="17" font-weight="700" fill="{TITLE}">{esc(title)}</text>'
            f'{body}</svg>')


def stats_svg(s):
    rows = [("Total Stars", s["stars"], "★"), ("Total Commit (12 bln)", s["commits"], "●"),
            ("Total Pull Request", s["prs"], "⇄"), ("Total Issue", s["issues"], "!"),
            ("Pengikut", s["followers"], "♥"), ("Repositori Publik", s["repos"], "▤")]
    body = ""
    for i, (label, val, icon) in enumerate(rows):
        y = 66 + i * 25
        body += (f'<text x="26" y="{y}" font-family="{FONT}" font-size="13" fill="{ACCENT}">{icon}</text>'
                 f'<text x="50" y="{y}" font-family="{FONT}" font-size="13" fill="{MUTED}">{esc(label)}:</text>'
                 f'<text x="228" y="{y}" font-family="{FONT}" font-size="13" font-weight="700" fill="{TEXT}">{val:,}</text>')
    g, frac = grade(s)
    cx, cy, r = 392, 108, 42
    circ = 2 * math.pi * r
    body += (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{BORDER}" stroke-width="8"/>'
             f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{ACCENT2}" stroke-width="8" stroke-linecap="round" '
             f'stroke-dasharray="{circ*frac:.1f} {circ:.1f}" transform="rotate(-90 {cx} {cy})"/>'
             f'<text x="{cx}" y="{cy+9}" text-anchor="middle" font-family="{FONT}" font-size="28" font-weight="800" fill="{TEXT}">{esc(g)}</text>')
    return card(470, 215, body, f"Statistik GitHub {s['name']}")


def languages_svg(s):
    langs = sorted(s["langs"].items(), key=lambda kv: -kv[1]["size"])
    total = sum(v["size"] for _, v in langs) or 1
    top = langs[:6]
    other = sum(v["size"] for _, v in langs[6:])
    items = [(n, v["size"], v["color"]) for n, v in top]
    if other:
        items.append(("Lainnya", other, "#8b98b8"))
    body, x, bar_w = "", 24, 292
    body += f'<clipPath id="c"><rect x="24" y="52" width="{bar_w}" height="10" rx="5"/></clipPath><g clip-path="url(#c)">'
    for n, size, color in items:
        w = bar_w * size / total
        body += f'<rect x="{x:.1f}" y="52" width="{w:.1f}" height="10" fill="{esc(color)}"/>'
        x += w
    body += "</g>"
    if not items:
        body += f'<text x="24" y="92" font-family="{FONT}" font-size="13" fill="{MUTED}">Belum ada kode publik.</text>'
    for i, (n, size, color) in enumerate(items):
        col, row = i % 2, i // 2
        px, py = 24 + col * 150, 92 + row * 26
        body += (f'<circle cx="{px+5}" cy="{py-4}" r="5" fill="{esc(color)}"/>'
                 f'<text x="{px+16}" y="{py}" font-family="{FONT}" font-size="12.5" fill="{TEXT}">{esc(n)} '
                 f'<tspan fill="{MUTED}">{100*size/total:.1f}%</tspan></text>')
    return card(340, 215, body, "Bahasa Paling Banyak Dipakai")


def donut_svg(langs, title):
    """Kartu donat: legenda di kiri, donat di kanan (5 bahasa teratas + 'Lainnya')."""
    ranked = sorted(langs.items(), key=lambda kv: -kv[1]["size"])
    items = [(n, v["size"], v["color"]) for n, v in ranked[:5]]
    other = sum(v["size"] for _, v in ranked[5:])
    if other:
        items.append(("Lainnya", other, "#8b98b8"))
    total = sum(s for _, s, _ in items)
    body = ""
    if not total:
        body += f'<text x="24" y="92" font-family="{FONT}" font-size="13" fill="{MUTED}">Belum ada data.</text>'
        return card(400, 215, body, title)
    for i, (n, size, color) in enumerate(items):
        y = 70 + i * 23
        body += (f'<rect x="24" y="{y-10}" width="12" height="12" rx="3" fill="{esc(color)}"/>'
                 f'<text x="44" y="{y}" font-family="{FONT}" font-size="13" fill="{TEXT}">{esc(n)}</text>')
    cx, cy, r, sw = 300, 122, 52, 24
    circ = 2 * math.pi * r
    offset = 0.0
    for n, size, color in items:
        length = circ * size / total
        gap = 1.5 if len(items) > 1 else 0
        body += (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{esc(color)}" stroke-width="{sw}" '
                 f'stroke-dasharray="{max(length-gap, 0.1):.2f} {circ:.2f}" stroke-dashoffset="{-offset:.2f}" '
                 f'transform="rotate(-90 {cx} {cy})"/>')
        offset += length
    return card(400, 215, body, title)


def nice_max(v):
    if v <= 4:
        return 4
    step = 10 ** math.floor(math.log10(v))
    for m in (1, 2, 2.5, 5, 10):
        if m * step >= v:
            return m * step
    return v


def activity_svg(points, labels, title):
    """points: list[int]; labels: list[(index, text)]"""
    w, h, left, right, top, bottom = 820, 280, 46, 20, 56, 40
    pw, ph = w - left - right, h - top - bottom
    ymax = nice_max(max(points) if points else 1)
    n = max(len(points), 2)
    xy = [(left + pw * i / (n - 1), top + ph * (1 - v / ymax)) for i, v in enumerate(points)]
    body = ""
    for k in range(5):
        gy = top + ph * k / 4
        body += (f'<line x1="{left}" y1="{gy:.1f}" x2="{w-right}" y2="{gy:.1f}" stroke="{BORDER}" stroke-width="1" stroke-dasharray="3 4"/>'
                 f'<text x="{left-8}" y="{gy+4:.1f}" text-anchor="end" font-family="{FONT}" font-size="11" fill="{MUTED}">{ymax*(4-k)/4:g}</text>')
    if xy:
        line = " ".join(f"{x:.1f},{y:.1f}" for x, y in xy)
        area = f"{left},{top+ph} {line} {xy[-1][0]:.1f},{top+ph}"
        body += (f'<defs><linearGradient id="a" x1="0" y1="0" x2="0" y2="1">'
                 f'<stop offset="0" stop-color="{ACCENT}" stop-opacity="0.35"/><stop offset="1" stop-color="{ACCENT}" stop-opacity="0"/></linearGradient></defs>'
                 f'<polygon points="{area}" fill="url(#a)"/>'
                 f'<polyline points="{line}" fill="none" stroke="{ACCENT}" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>')
        for x, y in (xy if len(xy) <= 40 else [xy[i] for i in range(0, len(xy), 4)]):
            body += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{BG}" stroke="{ACCENT}" stroke-width="1.8"/>'
    for idx, text in labels:
        lx = left + pw * idx / (n - 1)
        body += f'<text x="{lx:.1f}" y="{h-14}" text-anchor="middle" font-family="{FONT}" font-size="11" fill="{MUTED}">{esc(text)}</text>'
    body += (f'<text x="14" y="{top+ph/2:.0f}" transform="rotate(-90 14 {top+ph/2:.0f})" text-anchor="middle" '
             f'font-family="{FONT}" font-size="11" fill="{MUTED}">Kontribusi</text>')
    return card(w, h, body, title)


def activity_year_svg(s):
    days = s["days"][-371:]
    weeks = [days[i:i + 7] for i in range(0, len(days), 7)]
    pts = [sum(c for _, c in wk) for wk in weeks]
    labels, last = [], None
    for i, wk in enumerate(weeks):
        m = wk[0][0].strftime("%b")
        if m != last:
            last = m
            if labels and i - labels[-1][0] < 3:   # hindari label saling menimpa
                labels.pop()
            labels.append((i, m))
    return activity_svg(pts, labels, f"Grafik Kontribusi {s['name']}")


def activity_30d_svg(s):
    days = s["days"][-30:]
    pts = [c for _, c in days]
    labels = [(i, d.strftime("%d %b")) for i, (d, _) in enumerate(days) if i % 5 == 0]
    return activity_svg(pts, labels, "Aktivitas 30 Hari Terakhir")


def placeholder_svg(w, h, title):
    body = (f'<text x="{w/2}" y="{h/2+4}" text-anchor="middle" font-family="{FONT}" font-size="13" fill="{MUTED}">'
            f'Menunggu update pertama. Jalankan workflow "Update Stats".</text>')
    return card(w, h, body, title)


# ----------------------------------------------------------------- main ----
def write(name, content):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, name), "w", encoding="utf-8") as f:
        f.write(content)
    print("ditulis:", name)


def main():
    if "--placeholder" in sys.argv:
        write("stats.svg", placeholder_svg(470, 215, "Statistik GitHub"))
        write("languages.svg", placeholder_svg(340, 215, "Bahasa Paling Banyak Dipakai"))
        write("lang-repo.svg", placeholder_svg(400, 215, "Bahasa Teratas per Repositori"))
        write("lang-commit.svg", placeholder_svg(400, 215, "Bahasa Teratas per Commit"))
        write("activity-year.svg", placeholder_svg(820, 280, "Grafik Kontribusi"))
        write("activity-30d.svg", placeholder_svg(820, 280, "Aktivitas 30 Hari Terakhir"))
        return
    token = os.environ.get("GITHUB_TOKEN")
    login = os.environ.get("GH_USER") or os.environ.get("GITHUB_REPOSITORY_OWNER")
    if not token or not login:
        raise SystemExit("Set GITHUB_TOKEN dan GH_USER (atau GITHUB_REPOSITORY_OWNER).")
    s = summarize(fetch(login, token))
    write("stats.svg", stats_svg(s))
    write("languages.svg", languages_svg(s))
    write("lang-repo.svg", donut_svg(s["repo_langs"], "Bahasa Teratas per Repositori"))
    write("lang-commit.svg", donut_svg(s["commit_langs"], "Bahasa Teratas per Commit (12 bln)"))
    write("activity-year.svg", activity_year_svg(s))
    write("activity-30d.svg", activity_30d_svg(s))


if __name__ == "__main__":
    main()
