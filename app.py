"""
AI Sports Engagement Content Agent — Dashboard v7
Run: streamlit run app.py
"""

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from schemas.content_schemas import Sport, Difficulty, ContentType
from core.generator import generate_item, generate_batch, generate_weekly_calendar, DEFAULT_WEEKLY_ROTATION
from core.dedup import get_recent_summaries
from core.insta_card import generate_card, generate_batch_zip

st.set_page_config(page_title="Sports Content Agent", page_icon="🏆", layout="wide")

# ---------- Platform-surface guidance (assignment explicitly asks: match format to Story/Feed/Reel) ----------
SURFACE_MAP = {
    "MCQ": "Story (Quiz sticker)",
    "True/False": "Story (Quiz sticker)",
    "This-or-That": "Story (Poll sticker)",
    "Fill-in-the-Blank": "Feed post / caption",
    "Guess-the-Number": "Story (Slider/Emoji sticker) or Feed caption",
}

TYPE_ICON = {
    "MCQ": "❓",
    "True/False": "⚖️",
    "This-or-That": "🗳️",
    "Fill-in-the-Blank": "✏️",
    "Guess-the-Number": "🔢",
}

if "batch" not in st.session_state:
    st.session_state.batch = []
if "errors" not in st.session_state:
    st.session_state.errors = []
if "revealed" not in st.session_state:
    st.session_state.revealed = {}  # item_id -> True once answer is revealed
if "calendar" not in st.session_state:
    st.session_state.calendar = []
if "calendar_errors" not in st.session_state:
    st.session_state.calendar_errors = []

# ---------------- Sidebar: generation controls ----------------
with st.sidebar:
    st.title("🏆 Content Agent")
    st.caption("AI-powered multi-format sports engagement content")

    st.divider()
    st.subheader("Generate")

    sport = st.selectbox("Sport", [s.value for s in Sport])
    difficulty = st.selectbox("Difficulty", [d.value for d in Difficulty], index=1)

    content_types = st.multiselect(
        "Content type(s) — mix multiple for a varied batch",
        [c.value for c in ContentType],
        default=[ContentType.MCQ.value],
        format_func=lambda x: f"{TYPE_ICON.get(x,'')} {x}",
    )
    batch_size = st.slider("Batch size", 1, 10, 5)

    generate_clicked = st.button("🚀 Generate Batch", use_container_width=True, type="primary")

    st.divider()
    st.subheader("Weekly Calendar")
    st.caption("One click → a full week's posting plan, one content type per day (rotated for variety).")
    calendar_clicked = st.button("📅 Generate Weekly Calendar", use_container_width=True)

    st.divider()
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🗑️ Clear", use_container_width=True):
            st.session_state.batch = []
            st.session_state.errors = []
            st.rerun()
    with col_b:
        st.button("📋 Copy all", use_container_width=True, disabled=True, help="Export coming soon")

    st.divider()
    with st.expander("ℹ️ How content is sourced"):
        st.markdown(
            "- **Web search** → fresh/recent facts (records, transfers, results)\n"
            "- **Vector DB (ChromaDB)** → stable/historical facts\n"
            "- **This-or-That** → opinion-based, never fact-checked\n\n"
            "Each item shows its source below the content."
        )

if generate_clicked:
    if not content_types:
        st.sidebar.error("Select at least one content type.")
    else:
        with st.spinner(f"Generating {batch_size} item(s) for {sport}..."):
            result = generate_batch(sport, content_types, difficulty, batch_size)
            st.session_state.batch = result["items"]
            st.session_state.errors = result["errors"]

if calendar_clicked:
    with st.spinner(f"Building a week of content for {sport}... (7 items, one per day)"):
        result = generate_weekly_calendar(sport, difficulty)
        st.session_state.calendar = result["calendar"]
        st.session_state.calendar_errors = result["errors"]

# ---------------- Main area: tabs ----------------
tab_generate, tab_calendar, tab_history, tab_stats = st.tabs(
    ["📦 Current Batch", "📅 Weekly Calendar", "🕘 Recent History", "📊 Stats"]
)

# ===== TAB 1: Current batch =====
with tab_generate:
    if st.session_state.errors:
        for err in st.session_state.errors:
            st.warning(f"⚠️ Couldn't generate a {err['content_type']} item: {err['error']}")

    if not st.session_state.batch:
        st.info("👈 Configure options in the sidebar and click **Generate Batch** to start.")
    else:
        st.subheader(f"{sport} · {len(st.session_state.batch)} item(s) generated")

        batch_zip = generate_batch_zip(st.session_state.batch)
        st.download_button(
            "📦 Download All as Instagram Cards (ZIP)",
            data=batch_zip,
            file_name=f"{sport}_batch_content.zip",
            mime="application/zip",
            use_container_width=True,
        )
        st.divider()

        for i, item in enumerate(st.session_state.batch):
            ctype = item["content_type"]
            icon = TYPE_ICON.get(ctype, "•")
            surface = SURFACE_MAP.get(ctype, "")
            item_id = item.get("item_id", str(i))
            is_revealed = st.session_state.revealed.get(item_id, False)

            with st.container(border=True):
                header_col, badge_col, action_col = st.columns([3, 2, 1])
                with header_col:
                    st.markdown(f"**{icon} #{i+1} · {ctype}**")
                with badge_col:
                    st.caption(f"📱 Best for: {surface}")
                with action_col:
                    if st.button("🔄 Regenerate", key=f"regen_{i}", use_container_width=True):
                        with st.spinner("Regenerating..."):
                            try:
                                new_item = generate_item(item["sport"], ctype, item.get("difficulty", "Medium"))
                                st.session_state.batch[i] = new_item
                                st.session_state.revealed.pop(item_id, None)
                                st.rerun()
                            except RuntimeError as e:
                                st.error(str(e))

                st.markdown("")  # spacing

                # ---- Question/prompt shown WITHOUT the answer marked ----
                if ctype == "MCQ":
                    st.markdown(f"##### {item['question']}")
                    choice = st.radio(
                        "Choose an answer", item["options"], key=f"choice_{item_id}",
                        index=None, label_visibility="collapsed",
                    )
                elif ctype == "True/False":
                    st.markdown(f"##### {item['statement']}")
                    choice = st.radio(
                        "Your answer", ["True", "False"], key=f"choice_{item_id}",
                        index=None, horizontal=True, label_visibility="collapsed",
                    )
                elif ctype == "This-or-That":
                    st.markdown(f"##### {item['prompt']}")
                    c1, c2 = st.columns(2)
                    c1.info(f"🅰️ {item['options'][0]}")
                    c2.info(f"🅱️ {item['options'][1]}")
                    st.caption("🗳️ Opinion-based — not fact-checked, pure engagement")
                elif ctype == "Fill-in-the-Blank":
                    st.markdown(f"##### {item['sentence_with_blank']}")
                    choice = st.radio(
                        "Choose an answer", item["options"], key=f"choice_{item_id}",
                        index=None, label_visibility="collapsed",
                    )
                elif ctype == "Guess-the-Number":
                    st.markdown(f"##### {item['question']}")
                    guess = st.number_input(
                        "Your guess", key=f"guess_{item_id}", value=0, label_visibility="collapsed",
                    )

                # ---- Reveal control (skip for This-or-That, no correct answer) ----
                if ctype != "This-or-That":
                    reveal_col, _ = st.columns([1, 3])
                    with reveal_col:
                        if not is_revealed:
                            if st.button("👁️ Reveal Answer", key=f"reveal_{item_id}", use_container_width=True):
                                st.session_state.revealed[item_id] = True
                                st.rerun()

                    if is_revealed:
                        if ctype == "MCQ" or ctype == "Fill-in-the-Blank":
                            for opt in item["options"]:
                                marker = "✅" if opt == item["correct_answer"] else "▫️"
                                st.write(f"{marker} {opt}")
                        elif ctype == "True/False":
                            st.write(f"**Answer:** {'✅ True' if item['correct_answer'] else '❌ False'}")
                        elif ctype == "Guess-the-Number":
                            st.write(f"**Target:** {item['target_number']}  (± {item['tolerance']})")
                        st.caption(f"💡 {item.get('explanation', '')}")

                diff_tag = f" · {item.get('difficulty')}" if item.get("difficulty") else ""
                verify_badge = "✅ Web-verified" if item.get("web_verified") else "⚠️ Unverified"
                if ctype == "This-or-That":
                    verify_badge = "🗳️ Opinion (not fact-checked)"
                st.caption(
                    f"{verify_badge} · Source: `{item['source_type']}`{diff_tag} — {item['source_detail'][:80]}"
                )

                with st.expander("🔍 Show me why (grounding & verification detail)"):
                    st.markdown(f"**Retrieval source:** `{item['source_type']}` — {item['source_detail']}")
                    if ctype != "This-or-That":
                        st.markdown(f"**Verification check:** {'Passed ✅' if item.get('web_verified') else 'Failed ⚠️'}")
                        st.markdown(f"**Reason:** {item.get('verification_note', 'n/a')}")
                        st.caption(
                            "Every fact is independently re-checked against a fresh, separate web "
                            "search at generation time — not just trusted from the original retrieval."
                        )
                    else:
                        st.caption("This-or-That is opinion-based by design and is never fact-checked.")

                # ---- Instagram post card (answer never printed on the image) ----
                png_bytes = generate_card(item)
                st.download_button(
                    "📸 Download Instagram Card",
                    data=png_bytes,
                    file_name=f"{item['sport']}_{ctype.replace('/', '-')}_{i+1}.png",
                    mime="image/png",
                    key=f"card_{item_id}",
                    use_container_width=True,
                )
                with st.expander("Preview card"):
                    st.image(png_bytes, width=300)

# ===== TAB: Weekly Calendar =====
with tab_calendar:
    if st.session_state.calendar_errors:
        for err in st.session_state.calendar_errors:
            st.warning(f"⚠️ {err['day']} ({err['content_type']}): {err['error']}")

    if not st.session_state.calendar:
        st.info(
            "👈 Click **Generate Weekly Calendar** in the sidebar for a full 7-day posting plan — "
            "one content type per day, rotated for variety, instead of a flat list of quizzes."
        )
        st.caption("Default rotation: " + " · ".join(f"{d} ({t})" for d, t in DEFAULT_WEEKLY_ROTATION))
    else:
        st.subheader(f"7-day content calendar · {sport}")

        all_calendar_items = []
        for day_block in st.session_state.calendar:
            day, ctype, day_items = day_block["day"], day_block["content_type"], day_block["items"]
            icon = TYPE_ICON.get(ctype, "•")
            surface = SURFACE_MAP.get(ctype, "")

            st.markdown(f"### {day} — {icon} {ctype}")
            st.caption(f"📱 Best for: {surface}")

            if not day_items:
                st.warning("No item generated for this day (see warnings above).")
                continue

            for item in day_items:
                item["_day"] = day  # tag for zip filename grouping
                all_calendar_items.append(item)
                with st.container(border=True):
                    main_text = {
                        "MCQ": item.get("question"),
                        "True/False": item.get("statement"),
                        "This-or-That": item.get("prompt"),
                        "Fill-in-the-Blank": item.get("sentence_with_blank"),
                        "Guess-the-Number": item.get("question"),
                    }.get(ctype, "")
                    st.write(main_text)
                    verify_badge = "✅ Web-verified" if item.get("web_verified") else "⚠️ Unverified"
                    if ctype == "This-or-That":
                        verify_badge = "🗳️ Opinion"
                    st.caption(f"{verify_badge} · `{item['source_type']}`")

            st.divider()

        if all_calendar_items:
            zip_bytes = generate_batch_zip(all_calendar_items)
            st.download_button(
                "📦 Download Full Week as Instagram Cards (ZIP)",
                data=zip_bytes,
                file_name=f"{sport}_weekly_content_calendar.zip",
                mime="application/zip",
                use_container_width=True,
                type="primary",
            )

with tab_history:
    st.subheader("Recently generated facts (used for dedup/freshness)")
    st.caption("This is what the agent checks against to avoid repeating itself — across all content types, per sport.")
    hist_sport = st.selectbox("Sport to inspect", [s.value for s in Sport], key="hist_sport")
    recents = get_recent_summaries(hist_sport, limit=20)
    if recents:
        for r in recents:
            st.write(f"• {r}")
    else:
        st.info("No history yet for this sport — generate a batch first.")

# ===== TAB 3: Stats =====
with tab_stats:
    st.subheader("This session")
    if st.session_state.batch:
        col1, col2, col3 = st.columns(3)
        col1.metric("Items generated", len(st.session_state.batch))
        col2.metric("Failed attempts", len(st.session_state.errors))
        web_count = sum(1 for i in st.session_state.batch if i["source_type"] == "web_search")
        col3.metric("From web search", web_count)

        type_counts = {}
        for i in st.session_state.batch:
            type_counts[i["content_type"]] = type_counts.get(i["content_type"], 0) + 1
        st.write("**Content type breakdown:**")
        st.bar_chart(type_counts)
    else:
        st.info("Generate a batch to see stats here.")
