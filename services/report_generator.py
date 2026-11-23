"""PDF (ReportLab) and Excel (OpenPyXL) report generation from an analytics context."""
from datetime import datetime
from xml.sax.saxutils import escape
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart

PURPLE, TEAL = colors.HexColor("#7C5CFC"), colors.HexColor("#20C997")


def _quality_rows(meta):
    return [[m["kind"].title(), m["name"], m["records"], m["duplicates"], m["missing"], m["invalid"],
             "Cleaned" if m["is_cleaned"] else "Raw"] for m in meta]


# ---------------- Excel ----------------
def _sheet(wb, title, header, rows):
    ws = wb.create_sheet(title)
    ws.append(header)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="7C5CFC")
        c.alignment = Alignment(horizontal="left")
    for r in rows:
        ws.append([None if (not isinstance(v, str) and pd.isna(v)) else (v.to_pydatetime() if isinstance(v, pd.Timestamp) else v) for v in r])
    for i, col in enumerate(ws.columns, 1):
        width = max((len(str(c.value)) for c in col if c.value is not None), default=8)
        ws.column_dimensions[get_column_letter(i)].width = min(60, width + 3)
    ws.freeze_panes = "A2"
    return ws


def generate_excel(ctx, path, account="", generated=None):
    generated = generated or datetime.now()
    wb = Workbook()
    wb.remove(wb.active)
    ws = _sheet(wb, "Overview", ["Metric", "Value"],
                [["Account", account or "-"], ["Report generated", generated.strftime("%Y-%m-%d %H:%M")]] +
                [[k["label"], k["value"] if k["value"] is not None else "Not available in uploaded data"] for k in ctx["kpis"]])
    fs, f, g = ctx["fstats"], ctx["followers"], ctx["following"]
    if f is not None and len(f):
        _sheet(wb, "Followers", ["Username", "Profile URL", "Followed date"], f[["username", "profile_url", "followed_at"]].values.tolist())
    if g is not None and len(g):
        _sheet(wb, "Following", ["Username", "Profile URL", "Followed date"], g[["username", "profile_url", "followed_at"]].values.tolist())
    if f is not None and g is not None and len(f) and len(g):
        fk, gk = f["username"].str.lower(), g["username"].str.lower()
        _sheet(wb, "Mutual Connections", ["Username", "Profile URL"], f[fk.isin(set(gk))][["username", "profile_url"]].values.tolist())
        nm = [[u, "You follow them; they do not follow you back"] for u in g[~gk.isin(set(fk))]["username"]] + \
             [[u, "They follow you; you do not follow them back"] for u in f[~fk.isin(set(gk))]["username"]]
        _sheet(wb, "Non-Mutual Connections", ["Username", "Relationship"], nm)
    p = ctx["posts"]
    if p is not None and len(p):
        _sheet(wb, "Posts", ["Date", "Type", "Caption", "Likes", "Comments", "Likes + comments", "Tier"],
               p.sort_values("posted_at", ascending=False)[["posted_at", "content_type", "caption", "likes", "comments", "interactions", "tier"]].values.tolist())
        if p["interactions"].notna().any():
            rows = [["Average likes per post", ctx["avg_likes"]], ["Average comments per post", ctx["avg_comments"]],
                    ["Engagement rate (%)", ctx["engagement_rate"]], ["Posts per month", ctx["posts_per_month"]], [], ["Top posts"]]
            ws = _sheet(wb, "Engagement Analysis", ["Item", "Value"], rows)
            ws.append(["Date", "Type", "Caption", "Likes", "Comments", "Likes + comments"])
            for r in ctx["top_posts"]:
                ws.append([r["date"], r["type"], r["caption"], r["likes"], r["comments"], r["interactions"]])
            if ctx["type_table"]:
                ws.append([]); ws.append(["Content type", "Posts", "Avg likes", "Avg comments", "Avg interactions"])
                for t in ctx["type_table"]:
                    ws.append([t["content_type"], t["posts"], t["avg_likes"], t["avg_comments"], t["avg_interactions"]])
    if ctx["meta"]:
        _sheet(wb, "Data Quality", ["Dataset", "Name", "Records", "Duplicates removed", "Missing values", "Invalid removed", "Version"], _quality_rows(ctx["meta"]))
    _sheet(wb, "Insights", ["Insight", "Detail"], [[i["title"], i["text"]] for i in ctx["insights"]])
    wb.save(path)
    return path


# ---------------- PDF ----------------
def _bar(labels, values, color=PURPLE, w=400, h=160):
    d = Drawing(w, h)
    c = VerticalBarChart()
    c.x, c.y, c.width, c.height = 40, 30, w - 60, h - 50
    c.data = [values]
    c.categoryAxis.categoryNames = labels
    c.categoryAxis.labels.fontSize = 7
    c.categoryAxis.labels.angle = 30 if len(labels) > 6 else 0
    c.categoryAxis.labels.boxAnchor = "ne" if len(labels) > 6 else "n"
    c.valueAxis.labels.fontSize = 7
    c.valueAxis.valueMin = 0
    c.bars[0].fillColor = color
    d.add(c)
    return d


def _table(data, widths=None, header=True):
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    st = [("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD2DC")),
          ("VALIGN", (0, 0), (-1, -1), "TOP")]
    if header:
        st += [("BACKGROUND", (0, 0), (-1, 0), PURPLE), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]
    t.setStyle(TableStyle(st))
    return t


def generate_pdf(ctx, path, account="", generated=None):
    generated = generated or datetime.now()
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], textColor=PURPLE, fontSize=24)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=PURPLE, spaceBefore=14)
    body, small = ss["BodyText"], ParagraphStyle("sm", parent=ss["BodyText"], fontSize=8, textColor=colors.grey)
    P = lambda t, s=body: Paragraph(escape(str(t)), s)
    el = [P("SocialPulse Analytics Report", h1),
          P(f"Account: {account or '-'}   |   Generated: {generated:%d %B %Y, %H:%M}", small), Spacer(1, 10),
          P("Account overview and KPIs", h2)]
    el.append(_table([["Metric", "Value"]] + [[k["label"], k["value"] if k["value"] is not None else "Not available in uploaded data"] for k in ctx["kpis"]],
                     [8 * cm, 8 * cm]))
    fs = ctx["fstats"]
    if fs["followers"] is not None or fs["following"] is not None:
        el.append(P("Followers and following", h2))
        if fs["followers"] is not None and fs["following"] is not None:
            el.append(_bar(["Followers", "Following"], [fs["followers"], fs["following"]], TEAL, 300, 140))
            el.append(_table([["Mutual", "You follow, no follow-back", "Follow you, you don't follow back", "Follower/following ratio"],
                              [fs["mutual"], fs["not_following_back"], fs["fans"], fs["ratio"]]]))
        else:
            el.append(P("Only one of followers/following was imported, so connection comparisons are not available."))
        if ctx["growth"]:
            g = ctx["growth"]
            el.append(Spacer(1, 6))
            el.append(P(f"Follower snapshots: {g['from']} to {g['to']}: {g['new']} accounts only in the newer snapshot, {g['lost']} only in the older."))
    if ctx["caps"]["posts"]:
        el.append(P("Content performance", h2))
        ph = ctx["charts"].get("posting_frequency", {})
        if "labels" in ph:
            el.append(P("Posts per month", small))
            el.append(_bar(ph["labels"][-12:], ph["series"][0]["data"][-12:]))
        if ctx["top_posts"]:
            has_i = ctx["top_posts"][0]["interactions"] is not None
            el.append(P("Top posts by likes + comments" if has_i else "Most recent posts (engagement counts not in export)", small))
            rows = [["Date", "Type", "Caption", "Likes", "Comments", "Total"]] + [
                [Paragraph(escape(str(r[k])), small) if k == "caption" else ("-" if r[k] is None else r[k])
                 for k in ("date", "type", "caption", "likes", "comments", "interactions")] for r in ctx["top_posts"]]
            el.append(_table(rows, [2.3 * cm, 1.8 * cm, 7 * cm, 1.5 * cm, 2 * cm, 1.6 * cm]))
        if ctx["type_table"]:
            el.append(Spacer(1, 8))
            el.append(_table([["Content type", "Posts", "Avg likes", "Avg comments", "Avg interactions"]] +
                             [[t["content_type"], t["posts"], t["avg_likes"], t["avg_comments"], t["avg_interactions"]] for t in ctx["type_table"]]))
    if ctx["meta"]:
        el.append(P("Data quality summary", h2))
        el.append(_table([["Dataset", "Name", "Records", "Dupes", "Missing", "Invalid", "Version"]] +
                         [[r[0], Paragraph(escape(str(r[1])), small)] + r[2:] for r in _quality_rows(ctx["meta"])],
                         [2 * cm, 5 * cm, 2 * cm, 1.8 * cm, 2 * cm, 2 * cm, 2 * cm]))
    el.append(P("Analytical insights", h2))
    for i in ctx["insights"]:
        el.append(Paragraph(f"<b>{escape(i['title'])}.</b> {escape(i['text'])}", body))
        el.append(Spacer(1, 4))
    el.append(Spacer(1, 10))
    el.append(P("Figures come only from the data you uploaded. Metrics missing from your export are shown as unavailable, not estimated.", small))
    SimpleDocTemplate(path, pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm, topMargin=1.8 * cm, bottomMargin=1.8 * cm,
                      title="SocialPulse Report").build(el)
    return path
