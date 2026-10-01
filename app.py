"""
AI Job Agent - Unified, High-Performance Streamlit Dashboard.

Includes only:
1. Upload Resume
2. Search Jobs
3. Top Matches
4. Generate ATS Resume
5. Generate Cover Letter
6. Generate Recruiter Email
7. Apply
8. Tracker
"""

import json
import os
import re
import sys
from datetime import date
from pathlib import Path
import streamlit as st

# Ensure backend modules are on sys.path
backend_path = Path(__file__).resolve().parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from tools.resume_parser import ResumeParser
from services.remoteok import RemoteOK
from services.job_search import JobSearchService
from services.daily_job_tracker import DailyJobTracker
from match_agent import analyze_match
from services.resume_generator import ATSResumeGenerator
from services.cover_letter_generator import CoverLetterGenerator
from agents.email_agent import EmailAgent
from services.application_automator import ApplicationAutomator, _detect_platform
from database.db import db
from database.models import ApplicationCreate, ApplicationStatus, ApplicationUpdate

st.set_page_config(
    page_title="AI Job Agent",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom High-End Styling
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* Header Banner */
.hero-banner {
    background: linear-gradient(135deg, #4F46E5 0%, #6366F1 50%, #8B5CF6 100%);
    padding: 1.75rem 2rem;
    border-radius: 16px;
    color: white;
    margin-bottom: 1.75rem;
    box-shadow: 0 10px 25px -5px rgba(99, 102, 241, 0.25);
}
.hero-banner h1 {
    color: white !important;
    font-weight: 800;
    font-size: 2.1rem;
    margin: 0;
    letter-spacing: -0.02em;
}
.hero-banner p {
    color: rgba(255, 255, 255, 0.9);
    font-size: 1rem;
    margin: 0.35rem 0 0 0;
}

/* Modern Card Box */
.card-box {
    background: #ffffff;
    border: 1px solid #E2E8F0;
    border-radius: 14px;
    padding: 1.5rem;
    margin-bottom: 1.25rem;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.02), 0 1px 2px rgba(0, 0, 0, 0.03);
    transition: all 0.2s ease-in-out;
}
.card-box:hover {
    border-color: #CBD5E1;
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05);
}

/* Skill Tags */
.skill-tag-matched {
    display: inline-block;
    background: #ECFDF5;
    color: #065F46;
    border: 1px solid #A7F3D0;
    padding: 0.3rem 0.75rem;
    border-radius: 9999px;
    font-size: 0.85rem;
    font-weight: 600;
    margin: 0.25rem;
}
.skill-tag-missing {
    display: inline-block;
    background: #FFF1F2;
    color: #9F1239;
    border: 1px solid #FECDD3;
    padding: 0.3rem 0.75rem;
    border-radius: 9999px;
    font-size: 0.85rem;
    font-weight: 600;
    margin: 0.25rem;
}
.skill-tag-general {
    display: inline-block;
    background: #F1F5F9;
    color: #334155;
    border: 1px solid #E2E8F0;
    padding: 0.25rem 0.65rem;
    border-radius: 9999px;
    font-size: 0.82rem;
    font-weight: 500;
    margin: 0.2rem;
}

/* Status Badges */
.status-pill {
    padding: 0.35rem 0.85rem;
    border-radius: 9999px;
    font-size: 0.8rem;
    font-weight: 700;
    display: inline-block;
    letter-spacing: 0.03em;
    text-transform: uppercase;
}
.status-applied { background: #EFF6FF; color: #1D4ED8; border: 1px solid #BFDBFE; }
.status-interview { background: #FAF5FF; color: #7E22CE; border: 1px solid #E9D5FF; }
.status-offer { background: #ECFDF5; color: #047857; border: 1px solid #A7F3D0; }
.status-rejected { background: #FEF2F2; color: #B91C1C; border: 1px solid #FECACA; }

/* Portal Badges */
.portal-badge {
    display: inline-block;
    padding: 0.22rem 0.65rem;
    border-radius: 6px;
    font-size: 0.76rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin-right: 0.4rem;
    vertical-align: middle;
}
.portal-remoteok {
    background: #EEF2FF;
    color: #4338CA;
    border: 1px solid #C7D2FE;
}
.portal-remotive {
    background: #ECFDF5;
    color: #065F46;
    border: 1px solid #A7F3D0;
}
.portal-arbeitnow {
    background: #FAF5FF;
    color: #6B21A8;
    border: 1px solid #E9D5FF;
}
.portal-greenhouse {
    background: #ECFDF5;
    color: #065F46;
    border: 1px solid #A7F3D0;
}
.portal-ashby {
    background: #F5F3FF;
    color: #6D28D9;
    border: 1px solid #DDD6FE;
}
.portal-himalayas {
    background: #FFFBEB;
    color: #92400E;
    border: 1px solid #FDE68A;
}
.portal-weworkremotely {
    background: #FFF1F2;
    color: #9F1239;
    border: 1px solid #FECDD3;
}
.badge-india-eligible {
    display: inline-block;
    padding: 0.18rem 0.55rem;
    border-radius: 6px;
    background: #F0FDF4;
    color: #15803D;
    border: 1px solid #BBF7D0;
    font-size: 0.74rem;
    font-weight: 700;
    margin-right: 0.35rem;
    vertical-align: middle;
}

/* Daily Tracking Info Box */
.tracking-banner {
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-left: 4px solid #4F46E5;
    border-radius: 12px;
    padding: 1rem 1.4rem;
    margin-bottom: 1.25rem;
}
.keyword-chip {
    display: inline-block;
    background: #F1F5F9;
    color: #334155;
    border: 1px solid #CBD5E1;
    border-radius: 9999px;
    padding: 0.22rem 0.75rem;
    font-size: 0.82rem;
    font-weight: 600;
    margin: 0.2rem;
}

/* Metrics & Stats Card */
.stat-card {
    background: #ffffff;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 1.1rem;
    text-align: center;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
}
.stat-card .stat-value {
    font-size: 1.8rem;
    font-weight: 800;
    color: #1E293B;
    margin: 0;
}
.stat-card .stat-label {
    font-size: 0.85rem;
    font-weight: 600;
    color: #64748B;
    margin-top: 0.2rem;
}

/* Buttons */
.stButton > button {
    border-radius: 10px;
    font-weight: 600;
    padding: 0.5rem 1.25rem;
    transition: all 0.2s ease;
}
</style>
""", unsafe_allow_html=True)

# Session State Initialization
if "selected_job" not in st.session_state:
    st.session_state["selected_job"] = None
if "jobs" not in st.session_state:
    st.session_state["jobs"] = []
if "match_result" not in st.session_state:
    st.session_state["match_result"] = None
if "tailored_resume" not in st.session_state:
    st.session_state["tailored_resume"] = ""
if "cover_letter" not in st.session_state:
    st.session_state["cover_letter"] = ""
if "recruiter_email" not in st.session_state:
    st.session_state["recruiter_email"] = None
if "current_search_kw" not in st.session_state:
    st.session_state["current_search_kw"] = "Python AI"
if "last_searched_portal" not in st.session_state:
    st.session_state["last_searched_portal"] = "All Portals"


def get_current_profile() -> dict:
    """Reads candidate profile from data/profile.json."""
    p_path = Path("backend/data/profile.json")
    if not p_path.exists():
        p_path = Path("data/profile.json")
    if p_path.exists():
        try:
            with open(p_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


# ---------------- SIDEBAR NAVIGATION ----------------
st.sidebar.markdown("""
<div style="display: flex; align-items: center; gap: 10px; margin-bottom: 1.2rem;">
    <span style="font-size: 2rem;">💼</span>
    <div>
        <h2 style="margin: 0; font-size: 1.3rem; font-weight: 800; color: #1E293B;">AI Job Agent</h2>
        <span style="font-size: 0.75rem; color: #64748B; font-weight: 600;">Autonomous Career Copilot</span>
    </div>
</div>
""", unsafe_allow_html=True)

profile = get_current_profile()
if profile.get("name"):
    st.sidebar.markdown(f"""
    <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 10px; padding: 0.75rem; margin-bottom: 1rem;">
        <div style="font-weight: 700; color: #1E293B; font-size: 0.95rem;">👤 {profile.get('name')}</div>
        <div style="font-size: 0.78rem; color: #64748B; margin-top: 2px;">{profile.get('email', '')}</div>
        <div style="font-size: 0.75rem; color: #10B981; font-weight: 600; margin-top: 4px;">● Profile Active</div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.sidebar.info("💡 Upload your resume to activate matching.")

menu = st.sidebar.radio(
    "Navigation",
    [
        "Upload Resume",
        "Search Jobs",
        "Top Matches",
        "Generate ATS Resume",
        "Generate Cover Letter",
        "Generate Recruiter Email",
        "Apply",
        "Tracker",
    ]
)

st.sidebar.markdown("---")
st.sidebar.caption("⚡ Powered by Google Gemini & Playwright")


# ==================== 1. UPLOAD RESUME ====================
if menu == "Upload Resume":
    st.markdown("""
    <div class="hero-banner">
        <h1>📄 Upload Candidate Resume</h1>
        <p>Ingest your existing PDF resume to automatically parse skills, contact info, and career history.</p>
    </div>
    """, unsafe_allow_html=True)

    col_upload, col_preview = st.columns([1, 1], gap="large")

    with col_upload:
        st.subheader("Select Resume File")
        uploaded_file = st.file_uploader("Upload your resume in PDF format", type=["pdf"])

        if uploaded_file:
            upload_dir = Path("backend/uploads")
            upload_dir.mkdir(parents=True, exist_ok=True)
            file_path = upload_dir / uploaded_file.name

            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

            with st.spinner("Extracting resume content & structure..."):
                extracted_text = ResumeParser.extract_text(str(file_path))

                data_dir = Path("backend/data")
                data_dir.mkdir(parents=True, exist_ok=True)
                with open(data_dir / "resume.txt", "w", encoding="utf-8") as f:
                    f.write(extracted_text)

                email_match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", extracted_text)
                phone_match = re.search(r"(\+?\d[\d\s\-]{8,}\d)", extracted_text)
                linkedin_match = re.search(r"https?://(?:www\.)?linkedin\.com/in/[^\s]+", extracted_text)
                github_match = re.search(r"https?://(?:www\.)?github\.com/[^\s]+", extracted_text)

                lines = [l.strip() for l in extracted_text.splitlines() if l.strip()]
                name = lines[0] if lines else "Candidate"

                # Parse skills
                skills = []
                skills_section = re.search(r"(?:Core\s+)?Skills[:\n\r]+(.*?)(?:\n\s*\n|[A-Z][a-zA-Z\s]{2,}:|$)", extracted_text, re.IGNORECASE | re.DOTALL)
                if skills_section:
                    items = re.split(r"[\u2022\u2023\u25e6\u2043\u2219,\|\n]+", skills_section.group(1))
                    skills = [s.strip() for s in items if s.strip()]

                profile_data = {
                    "name": name,
                    "email": email_match.group(0) if email_match else "",
                    "phone": phone_match.group(0) if phone_match else "",
                    "linkedin": linkedin_match.group(0) if linkedin_match else "",
                    "github": github_match.group(0) if github_match else "",
                    "skills": skills,
                    "resume_path": str(file_path),
                    "resume_text": extracted_text,
                }

                with open(data_dir / "profile.json", "w", encoding="utf-8") as f:
                    json.dump(profile_data, f, indent=4, ensure_ascii=False)

            st.success(f"✅ Successfully processed & saved {uploaded_file.name}")
            profile = profile_data

    with col_preview:
        st.subheader("Current Candidate Profile")
        if profile.get("name"):
            st.markdown(f"""
            <div class="card-box">
                <div style="font-size: 1.3rem; font-weight: 800; color: #1E293B;">{profile.get('name')}</div>
                <div style="display: flex; flex-wrap: wrap; gap: 10px; margin-top: 0.5rem; font-size: 0.85rem; color: #64748B;">
                    <span>📧 {profile.get('email', 'N/A')}</span>
                    <span>📱 {profile.get('phone', 'N/A')}</span>
                    <span>🔗 {profile.get('linkedin', 'N/A')}</span>
                    <span>🐙 {profile.get('github', 'N/A')}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            skills_list = profile.get("skills", [])
            if skills_list:
                st.write("**Extracted Core Skills:**")
                chips_html = "".join([f'<span class="skill-tag-general">{s}</span>' for s in skills_list])
                st.markdown(chips_html, unsafe_allow_html=True)

            with st.expander("🔍 View Raw Extracted Text"):
                st.text(profile.get("resume_text", "No text stored."))
        else:
            st.info("No resume loaded yet. Please upload your PDF on the left.")


# ==================== 2. SEARCH JOBS ====================
elif menu == "Search Jobs":
    st.markdown("""
    <div class="hero-banner">
        <h1>🔍 Multi-Source Job Search & Target Company Pipeline</h1>
        <p>Live ingestion from remote-first target companies (<b>GitLab, Supabase, Canonical, Zapier, Wikimedia, Remote.com</b>) and verified aggregators (<b>Himalayas, WeWorkRemotely, Remotive, RemoteOK</b>) with strict <b>India eligibility filtering</b>.</p>
    </div>
    """, unsafe_allow_html=True)

    tracked_email = DailyJobTracker.get_tracked_email()
    tracked_kws = DailyJobTracker.get_tracked_keywords()

    # Tracking Status Banner
    st.markdown(f"""
    <div class="tracking-banner">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
            <div>
                <span style="font-size: 0.8rem; font-weight: 700; color: #4F46E5; text-transform: uppercase; letter-spacing: 0.05em;">● India Candidate Tracker Active</span>
                <div style="font-size: 1.15rem; font-weight: 800; color: #1E293B; margin-top: 2px;">
                    Tracking for: <u>{tracked_email}</u>
                </div>
            </div>
            <div style="display: flex; gap: 6px; flex-wrap: wrap; align-items: center;">
                <span class="badge-india-eligible">🇮🇳 India Eligible</span>
                <span class="portal-badge portal-greenhouse">🏛️ Greenhouse</span>
                <span class="portal-badge portal-ashby">⚡ Ashby</span>
                <span class="portal-badge portal-himalayas">🏔️ Himalayas</span>
                <span class="portal-badge portal-weworkremotely">💼 WWR</span>
                <span class="portal-badge portal-remotive">🎯 Remotive</span>
                <span class="portal-badge portal-remoteok">🌐 RemoteOK</span>
            </div>
        </div>
        <div style="margin-top: 0.6rem; font-size: 0.82rem; color: #64748B;">
            <b>Target Companies Monitored:</b> GitLab &bull; Canonical &bull; Supabase &bull; Zapier &bull; Wikimedia &bull; Remote.com &bull; Automattic &bull; Deel &bull; Postman &bull; DuckDuckGo
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Tracked Keywords Quick-Search Bar
    st.markdown("**🎯 Quick Search Tracked Keywords:**")
    kw_cols = st.columns(min(len(tracked_kws) + 1, 7))
    for idx, kw in enumerate(tracked_kws[:6]):
        with kw_cols[idx]:
            if st.button(f"🔎 {kw}", key=f"quick_kw_{idx}", use_container_width=True):
                st.session_state["current_search_kw"] = kw
                st.rerun()

    with kw_cols[-1]:
        if st.button("⚡ Scan All Today", type="secondary", use_container_width=True, help="Scan all tracked keywords across all portals right now"):
            with st.spinner(f"Running automated daily scan across target companies & feeds for {tracked_email}..."):
                scan_res = DailyJobTracker.run_daily_scan(email=tracked_email)
                st.session_state["jobs"] = scan_res.get("jobs", [])
                st.session_state["last_searched_portal"] = "All Sources (India Eligible)"
                st.success(f"✅ Daily scan complete! Discovered {scan_res.get('total_jobs_found', 0)} opportunities.")

    st.write("")

    # Search Bar Inputs
    col_q, col_portal, col_btn = st.columns([3.5, 1.7, 1], gap="medium")
    with col_q:
        current_kw = st.session_state.get("current_search_kw", "Python AI")
        search_query = st.text_input("Keywords, Skills, or Job Title", value=current_kw, placeholder="e.g. Python AI, AI Automation, AI Agents...")
    with col_portal:
        portal_options = JobSearchService.PORTALS
        selected_portal = st.selectbox("Search Feed / Category", portal_options, index=0)
    with col_btn:
        st.write("")
        st.write("")
        do_search = st.button("Search Jobs", type="primary", use_container_width=True)

    if do_search:
        st.session_state["current_search_kw"] = search_query
        with st.spinner(f"Querying [{selected_portal}] for '{search_query}' (India Verified)..."):
            jobs = JobSearchService.search(keyword=search_query, portal=selected_portal, max_total=50)
            st.session_state["jobs"] = jobs
            st.session_state["last_searched_portal"] = selected_portal
            DailyJobTracker.log_search(
                keyword=search_query,
                portal=selected_portal,
                jobs_count=len(jobs),
                email=tracked_email
            )

    # Job Results
    if st.session_state.get("jobs"):
        jobs_list = st.session_state["jobs"]
        portal_searched = st.session_state.get("last_searched_portal", "All Sources (India Eligible)")
        st.markdown(f"### Found **{len(jobs_list)}** Positions *(Filter: {portal_searched})*")

        for idx, job in enumerate(jobs_list):
            portal_name = job.get("portal", "RemoteOK")
            p_low = portal_name.lower()
            if "greenhouse" in p_low:
                badge_class = "portal-greenhouse"
                badge_icon = "🏛️"
            elif "ashby" in p_low:
                badge_class = "portal-ashby"
                badge_icon = "⚡"
            elif "himalayas" in p_low:
                badge_class = "portal-himalayas"
                badge_icon = "🏔️"
            elif "weworkremotely" in p_low:
                badge_class = "portal-weworkremotely"
                badge_icon = "💼"
            elif "remoteok" in p_low:
                badge_class = "portal-remoteok"
                badge_icon = "🌐"
            elif "remotive" in p_low:
                badge_class = "portal-remotive"
                badge_icon = "🎯"
            else:
                badge_class = "portal-arbeitnow"
                badge_icon = "🔍"

            with st.container():
                c_details, c_actions = st.columns([4, 1.3], gap="medium")
                with c_details:
                    st.markdown(f"""
                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px; flex-wrap: wrap;">
                        <span class="portal-badge {badge_class}">{badge_icon} {portal_name}</span>
                        <span class="badge-india-eligible">🇮🇳 India Eligible</span>
                        <span style="font-size: 1.15rem; font-weight: 700; color: #1E293B;">{job.get('title')}</span>
                        <span style="color: #64748B; font-weight: 600;">@ {job.get('company')}</span>
                    </div>
                    """, unsafe_allow_html=True)

                    tags_html = "".join([f'<span class="skill-tag-general">{t}</span>' for t in job.get('tags', [])[:5]])
                    loc_text = job.get('location', 'Remote')
                    date_info = f"&nbsp;&bull;&nbsp; 🗓️ `{job.get('date_posted')}`" if job.get('date_posted') else ""
                    st.markdown(f"📍 `{loc_text}` &nbsp; {tags_html} {date_info}", unsafe_allow_html=True)

                with c_actions:
                    if st.button(f"🎯 Target Job", key=f"job_btn_{idx}_{portal_name}", use_container_width=True):
                        st.session_state["selected_job"] = job
                        st.success(f"Selected: {job.get('title')}")
                    if job.get("url"):
                        st.markdown(f"[🔗 View Original Posting]({job.get('url')})")

                st.markdown("<hr style='margin: 0.8rem 0; border: none; border-top: 1px solid #E2E8F0;'>", unsafe_allow_html=True)

    # Tracked History & Keyword Management Expander
    st.write("")
    with st.expander(f"📊 Daily Keyword Tracking & Search History for {tracked_email}"):
        col_hist, col_manage = st.columns([3, 2], gap="large")

        with col_hist:
            st.markdown("#### 🕒 Recent Tracked Searches")
            history = DailyJobTracker.get_history(limit=10)
            if history:
                for h in history:
                    st.markdown(f"""
                    <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 0.6rem 0.9rem; margin-bottom: 0.5rem; display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <b>{h.get('keyword')}</b> &nbsp;<span style="font-size: 0.75rem; color: #64748B;">({h.get('portal')})</span>
                            <div style="font-size: 0.75rem; color: #94A3B8;">{h.get('timestamp')} &bull; {h.get('email')}</div>
                        </div>
                        <div style="font-weight: 700; color: #4F46E5; font-size: 0.95rem;">
                            {h.get('jobs_count', 0)} jobs
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.caption("No search history recorded yet.")

        with col_manage:
            st.markdown("#### ⚙️ Manage Tracked Keywords")
            new_kw = st.text_input("Add New Daily Keyword", placeholder="e.g. LangChain, LLM Engineer")
            if st.button("➕ Add to Daily Tracker", use_container_width=True):
                if new_kw.strip():
                    DailyJobTracker.add_tracked_keyword(new_kw.strip())
                    st.success(f"Added '{new_kw}' to daily tracker!")
                    st.rerun()

            st.write("**Currently Tracked Keywords:**")
            for kw in tracked_kws:
                c_k, c_d = st.columns([3, 1])
                c_k.write(f"• `{kw}`")
                if c_d.button("🗑️", key=f"del_kw_{kw}", help=f"Remove {kw}"):
                    DailyJobTracker.remove_tracked_keyword(kw)
                    st.rerun()


# ==================== 3. TOP MATCHES ====================
elif menu == "Top Matches":
    st.markdown("""
    <div class="hero-banner">
        <h1>🎯 AI Match Engine</h1>
        <p>Evaluate your profile against any Job Description using Google Gemini to get an objective match score and gap analysis.</p>
    </div>
    """, unsafe_allow_html=True)

    selected = st.session_state.get("selected_job")
    default_jd = selected.get("description", "") if selected else ""

    if selected:
        st.info(f"Targeting Selected Job: **{selected.get('title')}** @ **{selected.get('company')}**")

    jd_input = st.text_area("Target Job Description", value=default_jd, height=200, placeholder="Paste job requirements, responsibilities, or selected JD here...")

    if st.button("🚀 Analyze Match Fit", type="primary"):
        if not jd_input.strip():
            st.error("Please provide a Job Description to analyze.")
        else:
            with st.spinner("Analyzing candidate-job fit with Google Gemini..."):
                profile_path = "backend/data/profile.json" if Path("backend/data/profile.json").exists() else "data/profile.json"
                result = analyze_match(profile_path, jd_input)
                st.session_state["match_result"] = result

    match = st.session_state.get("match_result")
    if match:
        st.markdown("---")
        score = match.get("match_score", 0)
        rec = match.get("recommendation", "N/A")

        score_color = "#10B981" if score >= 75 else ("#F59E0B" if score >= 50 else "#EF4444")
        st.markdown(f"""
        <div class="card-box" style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap;">
            <div>
                <div style="font-size: 0.85rem; font-weight: 700; color: #64748B; text-transform: uppercase;">Match Score</div>
                <div style="font-size: 3rem; font-weight: 800; color: {score_color};">{score}%</div>
            </div>
            <div style="text-align: right;">
                <div style="font-size: 0.85rem; font-weight: 700; color: #64748B; text-transform: uppercase;">Recommendation</div>
                <div style="font-size: 1.3rem; font-weight: 800; color: #1E293B;">{rec}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"""
        <div class="card-box">
            <h4 style="margin: 0 0 0.5rem 0; color: #1E293B;">Executive Fit Summary</h4>
            <p style="margin: 0; color: #475569; line-height: 1.6;">{match.get('short_summary', 'No summary generated.')}</p>
        </div>
        """, unsafe_allow_html=True)

        col_matched, col_missing = st.columns(2, gap="medium")
        with col_matched:
            st.markdown("#### ✅ Matched Skills")
            matched = match.get("matched_skills", [])
            if matched:
                chips = "".join([f'<span class="skill-tag-matched">✓ {s}</span>' for s in matched])
                st.markdown(chips, unsafe_allow_html=True)
            else:
                st.info("No matching skills identified.")

        with col_missing:
            st.markdown("#### ⚠️ Missing / Required Gaps")
            missing = match.get("missing_skills", [])
            if missing:
                chips = "".join([f'<span class="skill-tag-missing">✗ {s}</span>' for s in missing])
                st.markdown(chips, unsafe_allow_html=True)
            else:
                st.success("No critical skill gaps identified!")


# ==================== 4. GENERATE ATS RESUME ====================
elif menu == "Generate ATS Resume":
    st.markdown("""
    <div class="hero-banner">
        <h1>📝 ATS Resume Generator</h1>
        <p>Restructure and emphasize existing achievements for the target role with zero invented credentials.</p>
    </div>
    """, unsafe_allow_html=True)

    selected = st.session_state.get("selected_job")
    default_jd = selected.get("description", "") if selected else ""
    target_jd = st.text_area("Target Job Description", value=default_jd, height=160, placeholder="Paste JD here to tailor your resume...")

    if st.button("✨ Tailor ATS Resume", type="primary"):
        if not target_jd.strip():
            st.error("Please provide a Job Description.")
        else:
            with st.spinner("Optimizing resume for ATS with Google Gemini..."):
                profile_path = "backend/data/profile.json" if Path("backend/data/profile.json").exists() else "data/profile.json"
                save_path = "backend/data/tailored_resume.txt"
                res = ATSResumeGenerator.generate_tailored_resume(
                    resume=profile_path,
                    job_description=target_jd,
                    save_path=save_path
                )
                st.session_state["tailored_resume"] = res.get("tailored_resume_text", "")
                st.success("ATS Resume tailored successfully!")

    if st.session_state["tailored_resume"]:
        st.markdown("---")
        st.subheader("Tailored ATS Resume (Editable Preview)")
        edited_resume = st.text_area("ATS Plaintext Resume", value=st.session_state["tailored_resume"], height=420)
        st.download_button(
            label="📥 Download ATS Resume (.txt)",
            data=edited_resume,
            file_name="tailored_ats_resume.txt",
            mime="text/plain",
            type="primary"
        )


# ==================== 5. GENERATE COVER LETTER ====================
elif menu == "Generate Cover Letter":
    st.markdown("""
    <div class="hero-banner">
        <h1>✉️ Cover Letter Generator</h1>
        <p>Craft a personalized, persuasive cover letter connecting your genuine achievements to company requirements.</p>
    </div>
    """, unsafe_allow_html=True)

    selected = st.session_state.get("selected_job")
    default_company = selected.get("company", "") if selected else ""
    default_role = selected.get("title", "") if selected else ""
    default_jd = selected.get("description", "") if selected else ""

    col1, col2 = st.columns(2)
    with col1:
        comp_name = st.text_input("Company Name", value=default_company, placeholder="Target Company")
    with col2:
        role_name = st.text_input("Role Title", value=default_role, placeholder="Position Title")

    target_jd = st.text_area("Job Description", value=default_jd, height=150, placeholder="Paste Job Description...")

    if st.button("✍️ Generate Custom Cover Letter", type="primary"):
        if not target_jd.strip():
            st.error("Please provide a Job Description.")
        else:
            with st.spinner("Drafting cover letter with Google Gemini..."):
                profile_path = "backend/data/profile.json" if Path("backend/data/profile.json").exists() else "data/profile.json"
                save_path = "backend/data/cover_letter.txt"
                res = CoverLetterGenerator.generate(
                    resume=profile_path,
                    job_description=target_jd,
                    company_name=comp_name,
                    role_title=role_name,
                    save_path=save_path
                )
                st.session_state["cover_letter"] = res.get("cover_letter_text", "")
                st.success("Cover letter generated!")

    if st.session_state["cover_letter"]:
        st.markdown("---")
        st.subheader("Generated Cover Letter")
        edited_letter = st.text_area("Letter Content", value=st.session_state["cover_letter"], height=380)
        st.download_button(
            label="📥 Download Cover Letter (.txt)",
            data=edited_letter,
            file_name="cover_letter.txt",
            mime="text/plain",
            type="primary"
        )


# ==================== 6. GENERATE RECRUITER EMAIL ====================
elif menu == "Generate Recruiter Email":
    st.markdown("""
    <div class="hero-banner">
        <h1>📬 Recruiter Outreach Email</h1>
        <p>Auto-detect recruiter emails from job postings and generate high-impact, concise outreach drafts.</p>
    </div>
    """, unsafe_allow_html=True)

    selected = st.session_state.get("selected_job")
    default_company = selected.get("company", "") if selected else ""
    default_role = selected.get("title", "") if selected else ""
    default_jd = selected.get("description", "") if selected else ""

    c1, c2 = st.columns(2)
    with c1:
        comp = st.text_input("Company Name", value=default_company)
    with c2:
        role = st.text_input("Role Title", value=default_role)

    jd_input = st.text_area("Job Posting Content", value=default_jd, height=150, placeholder="Paste full JD text to scan for recruiter contacts...")

    if st.button("📧 Generate Outreach Email", type="primary"):
        if not jd_input.strip():
            st.error("Please enter the Job Posting text.")
        else:
            with st.spinner("Scanning recruiter contact & drafting with Gemini..."):
                profile_path = "backend/data/profile.json" if Path("backend/data/profile.json").exists() else "data/profile.json"
                res = EmailAgent.generate_email(
                    resume=profile_path,
                    job=jd_input,
                    company_name=comp,
                    role_title=role,
                    save_path="backend/data/recruiter_email.txt"
                )
                st.session_state["recruiter_email"] = res
                st.success("Email draft ready!")

    mail = st.session_state.get("recruiter_email")
    if mail:
        st.markdown("---")
        if mail.get("has_recruiter_email"):
            st.success(f"🎯 Recruiter Email Detected: **{mail.get('recipient_email')}**")
        else:
            st.info("ℹ️ No direct email detected in posting. Cold application draft prepared.")

        st.text_input("Subject Line", value=mail.get("subject", ""), key="subj_inp")
        st.text_area("Email Body", value=mail.get("body", ""), height=280, key="body_inp")


# ==================== 7. APPLY ====================
elif menu == "Apply":
    st.markdown("""
    <div class="hero-banner">
        <h1>⚡ Application Automation</h1>
        <p>Automated submission via Playwright for <b>Greenhouse</b>, <b>Lever</b>, and <b>Ashby</b> with human checkpoint pause.</p>
    </div>
    """, unsafe_allow_html=True)

    selected = st.session_state.get("selected_job")
    default_url = selected.get("url", "") if selected else ""

    col_url, col_mode = st.columns([3, 1], gap="medium")
    with col_url:
        target_url = st.text_input("Job Application URL", value=default_url, placeholder="https://boards.greenhouse.io/... or https://jobs.lever.co/...")
    with col_mode:
        st.write("")
        st.write("")
        headless_mode = st.checkbox("Run Headless", value=False, help="Uncheck to view the browser fill forms in real-time.")

    if target_url:
        platform_detected = _detect_platform(target_url)
        st.caption(f"Detected Platform: **{platform_detected.capitalize()}**")

    if st.button("🚀 Launch Automated Application", type="primary"):
        if not target_url.strip():
            st.error("Please enter a valid application URL.")
        else:
            profile_path = "backend/data/profile.json" if Path("backend/data/profile.json").exists() else "data/profile.json"
            tailored_res = "backend/data/tailored_resume.txt" if Path("backend/data/tailored_resume.txt").exists() else "data/tailored_resume.txt"
            cover_path = "backend/data/cover_letter.txt" if Path("backend/data/cover_letter.txt").exists() else "data/cover_letter.txt"

            with st.spinner("Automating browser form population with Playwright..."):
                res = ApplicationAutomator.apply_to_job(
                    apply_url=target_url,
                    resume_profile=profile_path,
                    tailored_resume_path=tailored_res,
                    cover_letter_path=cover_path,
                    headless=headless_mode
                )

            status = res.get("status")
            if status == "ready_to_submit":
                st.success("✅ Application successfully filled and assets uploaded! Ready to submit.")
            elif status == "paused_for_user":
                st.warning(f"⏸️ Application Paused: {res.get('pause_reason')}")
            else:
                st.error(f"Execution notice: {res.get('error', status)}")

            c1, c2 = st.columns(2)
            with c1:
                st.write("**Fields Populated:**", ", ".join(res.get("fields_filled", [])))
                st.write("**Resume Attached:**", "✅ Yes" if res.get("resume_uploaded") else "❌ No")
            with c2:
                st.write("**Cover Letter Attached:**", "✅ Yes" if res.get("cover_letter_uploaded") else "❌ No")
                if res.get("unanswered_questions"):
                    st.write("**Pending Custom Questions:**", res.get("unanswered_questions"))

            # Save to tracker
            if st.button("💾 Save to Application Tracker"):
                comp = selected.get("company", "Target Company") if selected else "Target Company"
                r_title = selected.get("title", "Target Role") if selected else "Target Role"
                db.add_application(
                    ApplicationCreate(
                        company=comp,
                        role=r_title,
                        apply_url=target_url,
                        resume_version=tailored_res,
                        cover_letter_version=cover_path,
                        status=ApplicationStatus.APPLIED,
                        notes="Automated via Playwright"
                    )
                )
                st.success("Application successfully recorded in Tracker!")


# ==================== 8. TRACKER ====================
elif menu == "Tracker":
    st.markdown("""
    <div class="hero-banner">
        <h1>📊 Application Tracker</h1>
        <p>Monitor your job application pipeline, interview stages, and overall search velocity.</p>
    </div>
    """, unsafe_allow_html=True)

    # Metric Cards
    stats = db.get_stats()
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.markdown(f'<div class="stat-card"><div class="stat-value">{stats.get("total", 0)}</div><div class="stat-label">TOTAL APPLIED</div></div>', unsafe_allow_html=True)
    with m2:
        st.markdown(f'<div class="stat-card"><div class="stat-value" style="color: #3B82F6;">{stats.get("applied", 0)}</div><div class="stat-label">SUBMITTED</div></div>', unsafe_allow_html=True)
    with m3:
        st.markdown(f'<div class="stat-card"><div class="stat-value" style="color: #8B5CF6;">{stats.get("interview", 0)}</div><div class="stat-label">INTERVIEWS</div></div>', unsafe_allow_html=True)
    with m4:
        st.markdown(f'<div class="stat-card"><div class="stat-value" style="color: #10B981;">{stats.get("offer", 0)}</div><div class="stat-label">OFFERS</div></div>', unsafe_allow_html=True)
    with m5:
        st.markdown(f'<div class="stat-card"><div class="stat-value" style="color: #EF4444;">{stats.get("rejected", 0)}</div><div class="stat-label">REJECTED</div></div>', unsafe_allow_html=True)

    st.write("")

    f_col, a_col = st.columns([3, 1])
    with f_col:
        filter_status = st.selectbox("Filter Applications by Status", ["All", "Applied", "Interview", "Offer", "Rejected"])
    with a_col:
        st.write("")
        st.write("")
        if st.button("➕ Log Manual Application", use_container_width=True):
            st.session_state["show_manual_modal"] = not st.session_state.get("show_manual_modal", False)

    if st.session_state.get("show_manual_modal"):
        with st.form("manual_app_form"):
            st.markdown("#### Log New Application")
            m_comp = st.text_input("Company Name")
            m_role = st.text_input("Role Title")
            m_url = st.text_input("Apply Link")
            m_status = st.selectbox("Initial Status", ["Applied", "Interview", "Offer", "Rejected"])
            m_submit = st.form_submit_button("Save Application")
            if m_submit and m_comp and m_role:
                db.add_application(
                    ApplicationCreate(
                        company=m_comp,
                        role=m_role,
                        apply_url=m_url,
                        status=ApplicationStatus(m_status)
                    )
                )
                st.success("Application logged!")
                st.session_state["show_manual_modal"] = False
                st.rerun()

    status_query = None if filter_status == "All" else filter_status
    applications = db.get_all_applications(status=status_query)

    if not applications:
        st.info("No applications found matching the selected filter.")
    else:
        for app in applications:
            curr_status = app.get("status", "Applied")
            status_class = f"status-{curr_status.lower()}"

            with st.expander(f"{app.get('company')} — {app.get('role')}", expanded=False):
                col_left, col_right = st.columns([3, 2], gap="large")
                with col_left:
                    st.markdown(f'<span class="status-pill {status_class}">{curr_status}</span>', unsafe_allow_html=True)
                    st.write(f"**Applied Date:** `{app.get('applied_date')}`")
                    if app.get("apply_url"):
                        st.markdown(f"🔗 [View Application / Posting]({app.get('apply_url')})")
                    if app.get("resume_version"):
                        st.caption(f"Resume Version: {app.get('resume_version')}")
                    if app.get("cover_letter_version"):
                        st.caption(f"Cover Letter: {app.get('cover_letter_version')}")

                with col_right:
                    new_status = st.selectbox(
                        "Status",
                        ["Applied", "Interview", "Offer", "Rejected"],
                        index=["Applied", "Interview", "Offer", "Rejected"].index(curr_status) if curr_status in ["Applied", "Interview", "Offer", "Rejected"] else 0,
                        key=f"status_{app['id']}"
                    )
                    notes_val = st.text_area("Notes", value=app.get("notes") or "", height=80, key=f"notes_{app['id']}")

                    b_save, b_del = st.columns(2)
                    with b_save:
                        if st.button("Save", key=f"save_{app['id']}", use_container_width=True):
                            db.update_application(
                                app["id"],
                                ApplicationUpdate(status=ApplicationStatus(new_status), notes=notes_val)
                            )
                            st.success("Updated!")
                            st.rerun()
                    with b_del:
                        if st.button("Delete", key=f"del_{app['id']}", use_container_width=True):
                            db.delete_application(app["id"])
                            st.warning("Deleted!")
                            st.rerun()
