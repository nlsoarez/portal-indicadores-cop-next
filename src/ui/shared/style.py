from __future__ import annotations

import streamlit as st


def inject_global_style() -> None:
    st.markdown(
        """
        <style>
        :root { --claro:#ED1C24; --ink:#171717; --muted:#6B7280; --line:#E7E8EB; --surface:#F7F8FA; }
        .stApp { background:#fff; color:var(--ink); }
        [data-testid="stSidebar"] { background:#F7F8FA; border-right:1px solid var(--line); }
        .cop-eyebrow { font-size:.72rem; text-transform:uppercase; letter-spacing:.08em; color:var(--muted); font-weight:700; }
        .cop-title { font-size:1.8rem; line-height:1.1; font-weight:800; margin:.25rem 0 .35rem; }
        .cop-subtitle { color:var(--muted); margin-bottom:1.1rem; }
        .cop-role-admin { display:inline-block; border-radius:999px; padding:.25rem .6rem; background:#171717; color:#fff; font-size:.72rem; font-weight:700; }
        .cop-role-subadmin { display:inline-block; border-radius:999px; padding:.25rem .6rem; background:#EEF1F5; color:#343A40; font-size:.72rem; font-weight:700; }
        .cop-role-analyst { display:inline-block; border-radius:999px; padding:.25rem .6rem; background:#FDEBEC; color:#A41117; font-size:.72rem; font-weight:700; }
        div[data-testid="stMetric"] { border:1px solid var(--line); border-radius:14px; padding:.75rem 1rem; background:#fff; }
        .cop-tip { border-left:3px solid var(--claro); background:#FAFAFA; border-radius:0 10px 10px 0; padding:.75rem .9rem; margin:.4rem 0; }
        .cop-freshness-card { border:1px solid var(--line); border-radius:14px; padding:.8rem .9rem; background:#fff; min-height:104px; margin-bottom:.55rem; }
        .cop-freshness-name { color:var(--muted); font-size:.76rem; font-weight:650; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .cop-freshness-date { color:var(--ink); font-size:1rem; font-weight:800; margin-top:.3rem; }
        .cop-freshness-meta { color:#8A8F98; font-size:.68rem; margin-top:.35rem; line-height:1.35; }
        </style>
        """,
        unsafe_allow_html=True,
    )
