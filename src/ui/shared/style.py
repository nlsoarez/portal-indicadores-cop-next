from __future__ import annotations

import streamlit as st


def inject_global_style() -> None:
    st.markdown(
        """
        <style>
        :root {
            --cop-bg:#050b14;
            --cop-bg-2:#07111f;
            --cop-panel:#0b1727;
            --cop-panel-2:#0f2035;
            --cop-panel-soft:#10263d;
            --cop-text:#f4f7fb;
            --cop-muted:#91a2b7;
            --cop-line:rgba(148,163,184,.16);
            --cop-line-strong:rgba(148,163,184,.26);
            --cop-red:#ed1c24;
            --cop-red-2:#ff4050;
            --cop-cyan:#38bdf8;
            --cop-blue:#3b82f6;
            --cop-green:#31d58a;
            --cop-amber:#f7b84b;
            --cop-danger:#ff5d6c;
            --cop-shadow:0 18px 50px rgba(0,0,0,.28);
            --cop-radius:18px;
        }

        html, body, [class*="css"] {
            font-feature-settings:"ss01" 1, "cv02" 1, "cv03" 1;
        }

        .stApp {
            background:
                radial-gradient(circle at 85% -10%, rgba(37,99,235,.18), transparent 31%),
                radial-gradient(circle at 22% 0%, rgba(237,28,36,.14), transparent 24%),
                linear-gradient(180deg, var(--cop-bg) 0%, var(--cop-bg-2) 55%, #07101c 100%);
            color:var(--cop-text);
        }

        .stApp::before {
            content:"";
            position:fixed;
            inset:0;
            pointer-events:none;
            z-index:0;
            opacity:.23;
            background-image:
                linear-gradient(rgba(255,255,255,.018) 1px, transparent 1px),
                linear-gradient(90deg, rgba(255,255,255,.018) 1px, transparent 1px);
            background-size:42px 42px;
            mask-image:linear-gradient(to bottom, black, transparent 88%);
        }

        .main .block-container {
            position:relative;
            z-index:1;
            max-width:1680px;
            padding-top:1.6rem;
            padding-bottom:4rem;
        }

        header[data-testid="stHeader"] {
            background:transparent;
        }

        /* Sidebar / navigation */
        [data-testid="stSidebar"] {
            background:
                radial-gradient(circle at 18% 8%, rgba(237,28,36,.16), transparent 26%),
                linear-gradient(180deg, #07101c 0%, #081320 64%, #07101a 100%);
            border-right:1px solid rgba(148,163,184,.12);
        }

        [data-testid="stSidebar"] > div:first-child {
            padding-top:1rem;
        }

        [data-testid="stSidebar"] hr {
            border-color:var(--cop-line);
        }

        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] span {
            color:var(--cop-text);
        }

        [data-testid="stSidebar"] [data-testid="stRadio"] > div {
            gap:.32rem;
        }

        [data-testid="stSidebar"] [data-testid="stRadio"] label {
            border-radius:12px;
            padding:.58rem .7rem;
            border:1px solid transparent;
            transition:all .2s ease;
        }

        [data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
            background:rgba(255,255,255,.045);
            border-color:rgba(148,163,184,.12);
            transform:translateX(3px);
        }

        [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
            background:linear-gradient(90deg, rgba(237,28,36,.22), rgba(59,130,246,.09));
            border-color:rgba(237,28,36,.28);
            box-shadow:inset 3px 0 0 var(--cop-red), 0 10px 28px rgba(237,28,36,.10);
        }

        [data-testid="stSidebar"] button {
            border-radius:11px !important;
        }

        .cop-brand-shell {
            padding:.25rem .1rem 1.05rem;
            border-bottom:1px solid var(--cop-line);
            margin-bottom:.9rem;
        }

        .cop-brand-mark {
            display:flex;
            align-items:center;
            gap:.55rem;
        }

        .cop-brand-word {
            font-size:1.55rem;
            font-weight:850;
            letter-spacing:-.04em;
            color:#fff;
        }

        .cop-brand-pulse {
            width:10px;
            height:10px;
            border-radius:50%;
            background:var(--cop-red);
            box-shadow:0 0 0 0 rgba(237,28,36,.55);
            animation:copPulse 2.2s ease-out infinite;
        }

        .cop-brand-product {
            margin-top:.22rem;
            color:#dbe6f4;
            font-size:.76rem;
            font-weight:650;
        }

        .cop-brand-context {
            margin-top:.15rem;
            color:#718197;
            font-size:.64rem;
            letter-spacing:.12em;
        }

        .cop-user-mini {
            min-height:68px;
            border:1px solid var(--cop-line);
            border-radius:14px;
            padding:.72rem .78rem;
            margin-bottom:.9rem;
            background:
                linear-gradient(90deg, rgba(8,19,32,.97) 0%, rgba(8,19,32,.84) 68%, rgba(8,19,32,.20) 100%),
                var(--cop-mini-art) right center/auto 100% no-repeat;
        }

        .cop-user-mini strong {
            display:block;
            color:#fff;
            font-size:.78rem;
        }

        .cop-user-mini span {
            display:block;
            color:#8fa0b5 !important;
            font-size:.65rem;
            margin-top:.12rem;
        }

        /* Page chrome */
        .cop-page-head {
            display:flex;
            align-items:flex-end;
            justify-content:space-between;
            gap:1rem;
            margin:0 0 1.05rem;
            animation:copFadeUp .42s ease both;
        }

        .cop-page-eyebrow {
            color:var(--cop-cyan);
            text-transform:uppercase;
            letter-spacing:.12em;
            font-size:.66rem;
            font-weight:800;
            margin-bottom:.32rem;
        }

        .cop-page-title-row {
            display:flex;
            align-items:center;
            gap:.65rem;
            flex-wrap:wrap;
        }

        .cop-page-head h1 {
            margin:0;
            color:#fff;
            font-size:clamp(1.65rem, 2.2vw, 2.25rem);
            letter-spacing:-.035em;
            line-height:1.05;
        }

        .cop-page-head p {
            margin:.42rem 0 0;
            color:var(--cop-muted);
            font-size:.88rem;
            max-width:900px;
        }

        .cop-page-badge {
            display:inline-flex;
            align-items:center;
            border:1px solid rgba(56,189,248,.22);
            background:rgba(56,189,248,.08);
            color:#8edcff;
            border-radius:999px;
            padding:.25rem .56rem;
            font-size:.65rem;
            font-weight:750;
        }

        .cop-hero {
            position:relative;
            overflow:hidden;
            min-height:150px;
            border:1px solid rgba(148,163,184,.16);
            border-radius:20px;
            margin:.1rem 0 1.1rem;
            padding:1.45rem 1.55rem;
            background:
                linear-gradient(90deg, rgba(6,13,24,.98) 0%, rgba(6,13,24,.92) 38%, rgba(6,13,24,.30) 72%, rgba(6,13,24,.56) 100%),
                var(--cop-hero-art) right center/auto 100% no-repeat;
            box-shadow:var(--cop-shadow);
            isolation:isolate;
            animation:copFadeUp .48s ease both;
        }

        .cop-hero::after {
            content:"";
            position:absolute;
            inset:auto -10% -70% 22%;
            height:180px;
            background:radial-gradient(circle, rgba(237,28,36,.22), transparent 64%);
            filter:blur(12px);
            z-index:-1;
            animation:copGlow 5.5s ease-in-out infinite alternate;
        }

        .cop-hero-copy span {
            color:#85cfff;
            font-size:.68rem;
            font-weight:800;
            letter-spacing:.11em;
            text-transform:uppercase;
        }

        .cop-hero-copy h2 {
            max-width:580px;
            margin:.32rem 0 .35rem;
            color:#fff;
            font-size:clamp(1.55rem, 2.4vw, 2.4rem);
            line-height:1.02;
            letter-spacing:-.04em;
        }

        .cop-hero-copy p {
            max-width:600px;
            margin:0;
            color:#aebccd;
            font-size:.86rem;
        }

        .cop-hero-signal {
            position:absolute;
            right:1.15rem;
            bottom:1rem;
            display:flex;
            gap:.28rem;
        }

        .cop-hero-signal i {
            width:26px;
            height:3px;
            border-radius:999px;
            background:rgba(255,255,255,.18);
            overflow:hidden;
            position:relative;
        }

        .cop-hero-signal i::after {
            content:"";
            position:absolute;
            inset:0;
            background:linear-gradient(90deg, transparent, var(--cop-red), transparent);
            transform:translateX(-100%);
            animation:copScan 2.6s linear infinite;
        }

        .cop-hero-signal i:nth-child(2)::after { animation-delay:.35s; }
        .cop-hero-signal i:nth-child(3)::after { animation-delay:.7s; }

        /* Legacy title compatibility */
        .cop-eyebrow {
            color:var(--cop-cyan);
            font-size:.68rem;
            text-transform:uppercase;
            letter-spacing:.1em;
            font-weight:800;
        }

        .cop-title {
            color:#fff;
            font-size:1.85rem;
            line-height:1.08;
            font-weight:850;
            margin:.18rem 0 .3rem;
        }

        .cop-subtitle {
            color:var(--cop-muted);
            margin-bottom:1rem;
        }

        .cop-role-admin,
        .cop-role-subadmin,
        .cop-role-analyst {
            display:inline-flex;
            align-items:center;
            gap:.3rem;
            border-radius:999px;
            padding:.22rem .56rem;
            font-size:.63rem;
            font-weight:800;
            letter-spacing:.07em;
        }

        .cop-role-admin {
            color:#ffd8dc;
            background:rgba(237,28,36,.14);
            border:1px solid rgba(237,28,36,.23);
        }

        .cop-role-subadmin {
            color:#cfe9ff;
            background:rgba(59,130,246,.12);
            border:1px solid rgba(59,130,246,.23);
        }

        .cop-role-analyst {
            color:#c9f7e1;
            background:rgba(49,213,138,.10);
            border:1px solid rgba(49,213,138,.20);
        }

        /* Streamlit surfaces */
        div[data-testid="stMetric"] {
            border:1px solid var(--cop-line);
            border-radius:16px;
            padding:.85rem 1rem;
            background:
                linear-gradient(180deg, rgba(16,38,61,.82), rgba(10,24,40,.90));
            box-shadow:0 12px 30px rgba(0,0,0,.14);
            transition:transform .2s ease, border-color .2s ease, box-shadow .2s ease;
            animation:copFadeUp .45s ease both;
        }

        div[data-testid="stMetric"]:hover {
            transform:translateY(-2px);
            border-color:rgba(56,189,248,.26);
            box-shadow:0 16px 34px rgba(0,0,0,.20);
        }

        div[data-testid="stMetric"] label {
            color:#92a4b9 !important;
            font-size:.72rem !important;
            font-weight:700 !important;
        }

        div[data-testid="stMetric"] [data-testid="stMetricValue"] {
            color:#fff;
            font-weight:850;
            letter-spacing:-.03em;
        }

        div[data-testid="stDataFrame"] {
            border:1px solid var(--cop-line);
            border-radius:16px;
            overflow:hidden;
            background:rgba(11,23,39,.72);
            box-shadow:0 12px 30px rgba(0,0,0,.10);
        }

        [data-testid="stExpander"] {
            border:1px solid var(--cop-line) !important;
            border-radius:15px !important;
            background:rgba(11,23,39,.72) !important;
            overflow:hidden;
        }

        .stTabs [data-baseweb="tab-list"] {
            gap:.35rem;
            border-bottom:1px solid var(--cop-line);
        }

        .stTabs [data-baseweb="tab"] {
            height:40px;
            border-radius:10px 10px 0 0;
            padding:0 .8rem;
            color:#91a2b7;
        }

        .stTabs [aria-selected="true"] {
            background:rgba(237,28,36,.09);
            color:#fff !important;
            border-bottom:2px solid var(--cop-red);
        }

        div[data-baseweb="select"] > div,
        div[data-testid="stTextInput"] input,
        div[data-testid="stNumberInput"] input,
        div[data-testid="stTextArea"] textarea {
            color:#eef4fb !important;
            background:#0b1929 !important;
            border-color:var(--cop-line-strong) !important;
            border-radius:11px !important;
        }

        div[data-testid="stForm"] {
            border:1px solid var(--cop-line);
            border-radius:18px;
            background:rgba(9,22,37,.84);
            box-shadow:var(--cop-shadow);
            padding:1rem;
        }

        .stButton > button,
        .stDownloadButton > button,
        button[kind="primary"] {
            border-radius:11px !important;
            border:1px solid rgba(148,163,184,.18) !important;
            background:linear-gradient(135deg, #122940, #0d1e31) !important;
            color:#fff !important;
            transition:all .2s ease !important;
        }

        .stButton > button:hover,
        .stDownloadButton > button:hover {
            transform:translateY(-1px);
            border-color:rgba(56,189,248,.30) !important;
            box-shadow:0 10px 24px rgba(0,0,0,.18);
        }

        button[kind="primary"] {
            background:linear-gradient(135deg, var(--cop-red), #b80f1a) !important;
            border-color:rgba(255,255,255,.12) !important;
            box-shadow:0 10px 24px rgba(237,28,36,.18);
        }

        /* Shared/custom cards */
        .cop-freshness-card,
        .cop-emp-card,
        .cop-emp-average,
        .cop-val-card,
        .cop-val-sector-card,
        .cop-dpa-card,
        .cop-dpa-traffic,
        .cop-close-card,
        .cop-chat-card,
        .cop-cert-card,
        .cop-leader-card,
        .cop-dashboard-insight,
        .cop-prod-highlight,
        .cop-val-extreme,
        .cop-close-extreme {
            color:var(--cop-text) !important;
            background:
                linear-gradient(180deg, rgba(17,37,59,.92), rgba(9,22,37,.94)) !important;
            border-color:var(--cop-line) !important;
            box-shadow:0 14px 34px rgba(0,0,0,.16) !important;
            transition:transform .2s ease, border-color .2s ease, box-shadow .2s ease;
            animation:copFadeUp .45s ease both;
        }

        .cop-freshness-card:hover,
        .cop-emp-card:hover,
        .cop-val-card:hover,
        .cop-dpa-card:hover,
        .cop-close-card:hover,
        .cop-chat-card:hover,
        .cop-cert-card:hover,
        .cop-leader-card:hover,
        .cop-dashboard-insight:hover {
            transform:translateY(-2px);
            border-color:rgba(56,189,248,.24) !important;
            box-shadow:0 18px 38px rgba(0,0,0,.22) !important;
        }

        .cop-freshness-name,
        .cop-freshness-meta,
        .cop-emp-card-label,
        .cop-val-card-label,
        .cop-dpa-card-label,
        .cop-close-card-label,
        .cop-chat-card-label,
        .cop-cert-card-label,
        .cop-leader-stat,
        .cop-dashboard-label {
            color:#8fa0b6 !important;
        }

        .cop-freshness-date,
        .cop-emp-card-value,
        .cop-val-card-value,
        .cop-dpa-card-value,
        .cop-close-card-value,
        .cop-chat-card-value,
        .cop-cert-card-value {
            color:#f7fbff;
        }

        .cop-prod-sector-pill {
            color:#dfe9f5 !important;
            background:rgba(12,30,49,.82) !important;
            border-color:var(--cop-line) !important;
        }

        .cop-tip {
            border-left:3px solid var(--cop-red);
            background:rgba(237,28,36,.07);
            border-radius:0 10px 10px 0;
            padding:.75rem .9rem;
            margin:.4rem 0;
        }

        /* Login */
        .cop-login-hero {
            min-height:235px;
            border:1px solid var(--cop-line);
            border-radius:22px;
            padding:2rem 2.1rem;
            margin:2.4rem 0 1.1rem;
            background:
                linear-gradient(90deg, rgba(5,11,20,.98) 0%, rgba(5,11,20,.90) 42%, rgba(5,11,20,.24) 76%, rgba(5,11,20,.54) 100%),
                var(--cop-hero-art) right center/auto 100% no-repeat;
            box-shadow:var(--cop-shadow);
            overflow:hidden;
            position:relative;
            animation:copFadeUp .52s ease both;
        }

        .cop-login-hero::after {
            content:"";
            position:absolute;
            width:220px;
            height:220px;
            right:8%;
            bottom:-68%;
            border-radius:50%;
            background:rgba(237,28,36,.22);
            filter:blur(48px);
            animation:copGlow 5s ease-in-out infinite alternate;
        }

        .cop-login-copy {
            position:relative;
            z-index:2;
            max-width:620px;
        }

        .cop-login-copy span {
            color:#8fd9ff;
            font-size:.68rem;
            font-weight:800;
            letter-spacing:.12em;
            text-transform:uppercase;
        }

        .cop-login-copy h1 {
            color:#fff;
            font-size:clamp(2rem, 4vw, 3.6rem);
            max-width:580px;
            line-height:.98;
            letter-spacing:-.055em;
            margin:.55rem 0 .65rem;
        }

        .cop-login-copy p {
            color:#aab9ca;
            max-width:540px;
            font-size:.92rem;
        }

        /* Typography */
        h1, h2, h3, h4, h5, h6 {
            color:#f7faff;
            letter-spacing:-.025em;
        }

        p, li {
            color:#bdc9d7;
        }

        a {
            color:#7dd3fc;
        }

        /* Motion */
        @keyframes copFadeUp {
            from { opacity:0; transform:translateY(8px); }
            to { opacity:1; transform:translateY(0); }
        }

        @keyframes copPulse {
            0% { box-shadow:0 0 0 0 rgba(237,28,36,.45); }
            70% { box-shadow:0 0 0 9px rgba(237,28,36,0); }
            100% { box-shadow:0 0 0 0 rgba(237,28,36,0); }
        }

        @keyframes copGlow {
            from { opacity:.55; transform:scale(.95); }
            to { opacity:1; transform:scale(1.08); }
        }

        @keyframes copScan {
            from { transform:translateX(-110%); }
            to { transform:translateX(110%); }
        }

        @media (max-width: 900px) {
            .main .block-container {
                padding-left:1rem;
                padding-right:1rem;
            }

            .cop-hero {
                min-height:165px;
                background-position:72% center;
                background-size:auto 100%;
            }

            .cop-hero-copy {
                max-width:72%;
            }

            .cop-page-head h1 {
                font-size:1.7rem;
            }
        }

        @media (prefers-reduced-motion: reduce) {
            *,
            *::before,
            *::after {
                animation-duration:.001ms !important;
                animation-iteration-count:1 !important;
                scroll-behavior:auto !important;
                transition-duration:.001ms !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
