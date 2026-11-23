"""Synthetic demo data. Clearly labelled DEMO everywhere it is used; no real people."""
import numpy as np
import pandas as pd


def build_demo(today=None, seed=7):
    rng = np.random.RandomState(seed)
    today = pd.Timestamp(today or pd.Timestamp.now()).normalize()
    names = [f"demo_user_{i:03d}" for i in range(1, 421)]
    following = names[:300]
    final_followers = names[130:400]           # overlap with following: indices 130-299
    snaps = []
    for i, months_ago in enumerate([4, 3, 2, 1, 0]):
        keep = int(len(final_followers) * (0.62 + 0.095 * i))
        users = final_followers[:keep]
        date = today - pd.DateOffset(months=months_ago)
        dates = pd.to_datetime(date) - pd.to_timedelta(rng.randint(0, 400, len(users)), unit="D")
        snaps.append((date, pd.DataFrame({"username": users, "profile_url": [f"https://www.instagram.com/{u}" for u in users],
                                          "followed_at": dates})))
    fol_dates = today - pd.to_timedelta(rng.randint(0, 500, len(following)), unit="D")
    following_df = pd.DataFrame({"username": following, "profile_url": [f"https://www.instagram.com/{u}" for u in following],
                                 "followed_at": fol_dates})
    n = 96
    days = np.sort(rng.randint(0, 330, n))[::-1]
    dates = [today - pd.Timedelta(days=int(d), hours=int(rng.randint(8, 22))) for d in days]
    types = rng.choice(["photo", "reel", "carousel", "video"], n, p=[.35, .3, .25, .1])
    base = {"photo": 14, "reel": 30, "carousel": 20, "video": 11}
    likes = np.array([max(2, int(rng.normal(base[t], base[t] * .35))) for t in types])
    for idx in rng.choice(n, 4, replace=False):
        likes[idx] = int(likes[idx] * rng.uniform(3, 5))      # a few viral posts
    comments = np.array([int(l * rng.uniform(.02, .08)) for l in likes])
    posts = pd.DataFrame({"external_id": [f"demo_post_{i}" for i in range(n)],
                          "caption": [f"Demo post #{i + 1}: sample caption" for i in range(n)],
                          "content_type": types, "posted_at": dates, "likes": likes, "comments": comments,
                          "shares": pd.NA, "saves": pd.NA, "reach": pd.NA, "impressions": pd.NA})
    return {"followers_snapshots": snaps, "following": following_df, "posts": posts}
