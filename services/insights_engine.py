"""Plain-language insights. Every statement comes from a calculation on the user's data;
if the data needed is missing, no claim is made."""
import math
import numpy as np
import pandas as pd
from services.analytics_engine import WEEKDAY_NAMES


def _i(tone, title, text):
    return {"tone": tone, "title": title, "text": text}


def generate(ctx, posts):
    out, caps, fs = [], ctx["caps"], ctx["fstats"]
    if not (caps["followers"] or caps["following"] or caps["posts"]):
        return [_i("info", "No data yet", "Import an Instagram export to see insights.")]

    if fs["followers"] is not None and fs["following"] is not None:
        f, g = fs["followers"], fs["following"]
        if g > f:
            out.append(_i("warning", "You follow more accounts than follow you",
                          f"You follow {g - f:,} more accounts than you have followers ({g:,} vs {f:,}; ratio {fs['ratio']})."))
        elif f > g:
            out.append(_i("positive", "More followers than accounts followed",
                          f"You have {f - g:,} more followers than accounts you follow (ratio {fs['ratio']})."))
        if g:
            share = fs["not_following_back"] / g * 100
            if share >= 50:
                out.append(_i("warning", "Many accounts you follow don't follow back",
                              f"{share:.0f}% of the accounts you follow ({fs['not_following_back']:,}) do not appear in your followers list."))
            elif share < 25:
                out.append(_i("positive", "Most connections are mutual",
                              f"Only {share:.0f}% of the accounts you follow don't follow you back."))
        if f and fs["fans"] / f * 100 >= 50:
            out.append(_i("info", "Many followers aren't followed back",
                          f"{fs['fans'] / f * 100:.0f}% of your followers ({fs['fans']:,}) are accounts you don't follow."))
    gr = ctx.get("growth")
    if gr:
        net = gr["values"][-1] - gr["values"][-2]
        pct = net / gr["values"][-2] * 100 if gr["values"][-2] else 0
        out.append(_i("positive" if net >= 0 else "warning", "Follower change between snapshots",
                      f"Between {gr['from']} and {gr['to']} your follower list changed by {net:+,} ({pct:+.1f}%): "
                      f"{gr['new']:,} accounts appear only in the newer snapshot and {gr['lost']:,} only in the older one."))

    if caps["posts"] and posts is not None:
        n = len(posts)
        if not (caps["likes"] or caps["comments"]):
            out.append(_i("info", "Engagement can't be measured from this export",
                          f"Your {n:,} posts have no like or comment counts, so engagement insights are skipped rather than guessed."))
        if caps["dates"]:
            d = posts["posted_at"].dropna()
            span = (d.max() - d.min()).days if len(d) > 1 else 0
            if len(d) >= 10 and span >= 60:
                end = d.max()
                last = int(((d > end - pd.Timedelta(days=30)) & (d <= end)).sum())
                prev = int(((d > end - pd.Timedelta(days=60)) & (d <= end - pd.Timedelta(days=30))).sum())
                if last != prev:
                    change = f"{(last - prev) / prev * 100:+.0f}%" if prev else "up from none"
                    out.append(_i("positive" if last > prev else "warning", "Posting frequency changed",
                                  f"You posted {last} times in your latest 30 days of activity (to {end:%d %b %Y}) "
                                  f"versus {prev} in the 30 days before ({change})."))
            if len(d) >= 14:
                wd = d.dt.weekday.value_counts()
                top = int(wd.idxmax())
                share = wd.max() / len(d) * 100
                if share >= 25:
                    out.append(_i("info", f"Most posts go out on {WEEKDAY_NAMES[top]}",
                                  f"{share:.0f}% of your dated posts were published on {WEEKDAY_NAMES[top]}."))
        inter = posts.dropna(subset=["interactions"])
        if len(inter) >= 8:
            avg = inter["interactions"].mean()
            above = inter[inter["interactions"] >= 1.5 * avg]
            if len(above) and avg > 0:
                best = inter.loc[inter["interactions"].idxmax()]
                out.append(_i("positive", "Some posts beat your average",
                              f"{len(above)} of {len(inter)} posts got at least 1.5× your average of {avg:,.0f} likes + comments. "
                              f"Your best post reached {best['interactions']:,.0f} ({best['interactions'] / avg:.1f}× average)."))
            if caps["dates"]:
                dd = inter.dropna(subset=["posted_at"]).assign(wd=lambda x: x["posted_at"].dt.weekday)
                g = dd.groupby("wd")["interactions"].agg(["mean", "count"])
                g = g[g["count"] >= 3]
                if len(g) >= 2:
                    wd = int(g["mean"].idxmax())
                    lift = g.loc[wd, "mean"] / avg - 1
                    if lift >= 0.2:
                        out.append(_i("info", f"{WEEKDAY_NAMES[wd][:-1]} posts perform best",
                                      f"Posts published on {WEEKDAY_NAMES[wd]} average {g.loc[wd, 'mean']:,.0f} interactions, "
                                      f"{lift * 100:.0f}% above your overall average."))
            if caps["types"]:
                tt = ctx.get("type_table") or []
                tt = [t for t in tt if t["posts"] >= 3 and t["avg_interactions"] is not None]
                if len(tt) >= 2:
                    out.append(_i("info", f"{tt[0]['content_type'].title()} posts lead on engagement",
                                  f"{tt[0]['content_type'].title()} posts average {tt[0]['avg_interactions']:,.0f} interactions versus "
                                  f"{tt[-1]['avg_interactions']:,.0f} for {tt[-1]['content_type']} posts."))
        com = posts["comments"].dropna()
        if len(com) >= 10 and com.sum() > 0:
            k = max(1, math.ceil(len(com) * 0.1))
            share = com.sort_values(ascending=False).head(k).sum() / com.sum() * 100
            if share >= 40:
                out.append(_i("warning", "Comments are concentrated in a few posts",
                              f"Your top {k} posts ({k / len(com) * 100:.0f}% of posts) received {share:.0f}% of all comments."))
        if ctx.get("engagement_rate") is not None:
            out.append(_i("info", "Engagement rate", f"On average a post gets interactions equal to {ctx['engagement_rate']}% of your follower count."))
    return out or [_i("info", "Not enough data for insights", "Import more data (posts with dates and counts, followers and following).")]
