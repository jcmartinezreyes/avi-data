"""Presentation primitives for AviData's accessible, task-first interface.

No data access, calculations or mutations belong in this module. Native Streamlit
widgets retain keyboard, label, focus and form semantics.
"""
from html import escape


def get_theme_css():
    return '''<style>
:root{--avi-forest:#174EA6;--avi-green:#0B57D0;--avi-mint:#E8F0FE;--avi-ink:#202124;--avi-muted:#4D5766;--avi-line:#DADFE7;--avi-paper:#FFFFFF;--avi-bg:#F7F9FC}
.stApp{background:var(--avi-bg);color:var(--avi-ink)}
[data-testid="stHeader"]{background:var(--avi-bg)}
.block-container{max-width:1480px;padding-top:1.5rem;padding-bottom:3rem}
h1,h2,h3{color:var(--avi-ink);letter-spacing:-.025em}
h1{font-size:clamp(1.65rem,3vw,2.15rem)!important;font-weight:700!important;line-height:1.2!important}
h2{font-size:1.4rem!important}h3{font-size:1.2rem!important}
[data-testid="stSidebar"]{background:#EEF2F8;border-right:1px solid var(--avi-line)}
[data-testid="stSidebar"] .stButton>button{width:100%;min-height:44px;border-radius:12px;text-align:left;justify-content:flex-start;border-color:transparent;background:transparent;color:var(--avi-ink)}
[data-testid="stSidebar"] .stButton>button:hover{background:#E1EAF8;border-color:transparent}
[data-testid="stSidebar"] .stButton>button[kind="primary"]{background:#D3E3FD;color:#073B83;border-color:#C4D8F8;font-weight:700}
.avi-brand{font-size:1.15rem;font-weight:750;color:var(--avi-ink);letter-spacing:-.025em;margin:.25rem 0 1rem}
.avi-brand small{display:block;font-size:.7rem;font-weight:550;letter-spacing:.09em;text-transform:uppercase;margin-top:.25rem;color:var(--avi-muted)}
.avi-side-card{margin:.55rem 0 .75rem;padding:.85rem;border:1px solid var(--avi-line);border-radius:14px;background:var(--avi-paper)}
.avi-side-card .label,.avi-section-label{font-size:.68rem;letter-spacing:.08em;text-transform:uppercase;font-weight:700;color:var(--avi-muted)}
.avi-side-card .value{font-size:.9rem;font-weight:650;margin-top:.25rem;overflow-wrap:anywhere}
.avi-side-card .subvalue{font-size:.77rem;color:var(--avi-muted);line-height:1.5;margin-top:.2rem}
.avi-hero{display:flex;align-items:center;justify-content:space-between;gap:1rem;margin:0 0 1.25rem;padding:.25rem 0 1.1rem;border-bottom:1px solid var(--avi-line)}
.avi-hero h1{margin:0}.avi-hero .eyebrow{margin:0 0 .35rem;color:var(--avi-green);font-size:.68rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase}
.avi-hero .description{margin:.45rem 0 0;color:var(--avi-muted);font-size:.9rem;max-width:70ch;line-height:1.5}
.avi-role-pill,.avi-status{display:inline-flex;align-items:center;gap:.4rem;padding:.35rem .65rem;border-radius:999px;font-size:.78rem;font-weight:650;background:#E8F0FE;color:#174EA6;line-height:1.35}
.avi-status.pending{background:#FFF4DA;color:#754400}.avi-status.success{background:#E0F2E9;color:#155E3B}.avi-status.neutral{background:#EFF2F6;color:#445166}
.avi-day-summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.6rem;margin:.5rem 0 1rem;padding:0}.avi-day-summary>div{padding:.7rem .8rem;border:1px solid var(--avi-line);border-radius:12px;background:#FFF}.avi-day-summary dt{font-size:.76rem;line-height:1.4;color:var(--avi-muted)}.avi-day-summary dd{font-size:1.3rem;font-weight:650;color:var(--avi-ink);margin:.25rem 0 0}
.avi-context{background:#FFF;border:1px solid var(--avi-line);border-radius:14px;padding:1rem 1.1rem;margin:.3rem 0 1rem}
.avi-context .title{font-size:1rem;font-weight:700;margin:0 0 .4rem}.avi-context .meta{font-size:.86rem;color:var(--avi-muted);line-height:1.65;overflow-wrap:anywhere}
.avi-section-intro{margin:.65rem 0 1rem}.avi-section-intro h2{margin:0 0 .35rem;font-size:1.35rem!important}.avi-section-intro p{color:var(--avi-muted);margin:0;line-height:1.55;max-width:80ch;font-size:.9rem}
.avi-steps{display:flex;flex-wrap:wrap;gap:.55rem 1rem;list-style:none;margin:.3rem 0 1rem;padding:0}
.avi-steps li{display:flex;align-items:center;gap:.45rem;color:var(--avi-muted);font-size:.82rem}
.avi-steps .number{display:inline-grid;place-items:center;height:25px;width:25px;flex:none;border-radius:50%;background:#E8ECF2;font-size:.75rem;font-weight:700}
.avi-steps li.current{color:#073B83;font-weight:700}.avi-steps li.current .number{background:#0B57D0;color:white}
.avi-steps li.done .number{background:#D9E9DE;color:#155E3B}
[data-testid="stMetric"]{padding:.8rem 1rem;background:#FFF;border:1px solid var(--avi-line);border-radius:14px;box-shadow:none;min-width:0}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p{color:var(--avi-muted)!important}
[data-testid="stMetricLabel"]{color:var(--avi-muted);font-weight:550}[data-testid="stMetricValue"]{color:var(--avi-ink);font-weight:650;font-size:1.65rem}
.stButton>button,[data-testid="stFormSubmitButton"]>button,[data-testid="stDownloadButton"]>button{min-height:44px;border-radius:10px;font-weight:600;box-shadow:none}
.stButton>button[kind="primary"],[data-testid="stFormSubmitButton"]>button[kind="primary"]{background:var(--avi-green);border-color:var(--avi-green);color:#FFF}
[data-testid="stAppViewContainer"] input,[data-testid="stAppViewContainer"] textarea{color:var(--avi-ink);-webkit-text-fill-color:var(--avi-ink);caret-color:var(--avi-green)}
[data-baseweb="input"],[data-baseweb="select"]>div,[data-baseweb="textarea"]{background:#FFF!important;border-radius:10px!important}
[data-testid="stTextInput"] input,[data-testid="stNumberInput"] input,[data-testid="stDateInput"] input{min-height:42px}
button:focus-visible,input:focus-visible,textarea:focus-visible,[role="combobox"]:focus-visible,a:focus-visible{outline:3px solid #0B57D0!important;outline-offset:3px!important}
[data-testid="stForm"]{border:1px solid var(--avi-line);padding:1rem;border-radius:14px;background:#FFF}
[data-testid="stExpander"]{border-radius:12px;background:#FFF;border-color:var(--avi-line)}
[data-testid="stExpander"] summary{min-height:44px;align-items:center}
[data-testid="stDataFrame"],[data-testid="stTable"]{border:1px solid var(--avi-line);border-radius:12px;overflow:hidden}
.st-key-operation_navigation{margin-bottom:.8rem}.st-key-operation_navigation button{min-height:44px;border-radius:999px!important;font-weight:550}
.st-key-operation_navigation [aria-pressed="true"]{background:#D3E3FD!important;color:#073B83!important;border-color:#8FB5F3!important}
.avi-scroll-table{height:320px;overflow:auto;border:1px solid var(--avi-line);border-radius:14px;background:#FFF}
.avi-scroll-table table{margin:0;width:100%;border-collapse:separate;border-spacing:0}.avi-scroll-table th,.avi-scroll-table td{padding:.7rem .85rem;border:0;border-bottom:1px solid var(--avi-line);text-align:left}
.avi-scroll-table thead th{position:sticky;top:0;background:#EEF2F8;z-index:1}.avi-scroll-table tbody tr:nth-child(even){background:#F9FAFC}
@media(max-width:760px){.block-container{padding:1rem .8rem 2rem}.avi-hero{align-items:flex-start;flex-direction:column;gap:.6rem}.avi-hero .description{font-size:.86rem}.avi-context{padding:.85rem}.avi-steps{gap:.6rem}.avi-steps li{font-size:.76rem}[data-testid="stMetric"]{padding:.75rem}.avi-role-pill{white-space:normal}.st-key-operation_navigation button{min-height:44px;font-size:.8rem}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;animation:none!important;transition:none!important}}
</style>'''


def section_intro(title, description):
    import streamlit as st
    st.markdown('<div class="avi-section-intro"><h2>' + escape(str(title)) + '</h2><p>'
                + escape(str(description)) + '</p></div>', unsafe_allow_html=True)


def workflow_steps(labels, current=0):
    import streamlit as st
    items = []
    for index, label in enumerate(labels):
        state = 'current' if index == current else ('done' if index < current else '')
        marker = ' aria-current="step"' if index == current else ''
        items.append(f'<li class="{state}"{marker}><span class="number">{index + 1}</span>{escape(str(label))}</li>')
    st.markdown('<ol class="avi-steps" aria-label="Pasos de la tarea">' + ''.join(items) + '</ol>', unsafe_allow_html=True)


def context_card(title, metadata, status=None, tone='neutral'):
    import streamlit as st
    allowed_tone = tone if tone in ('neutral', 'pending', 'success') else 'neutral'
    pill = '<span class="avi-status ' + allowed_tone + '">' + escape(str(status)) + '</span>' if status else ''
    st.markdown('<div class="avi-context"><div class="title">' + escape(str(title)) + '</div><div class="meta">'
                + escape(str(metadata)) + '</div>' + pill + '</div>', unsafe_allow_html=True)
