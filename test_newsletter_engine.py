#!/usr/bin/env python3
"""
Unit tests for New World Grid Newsletter Engine ([aeOS:Home:Newsletter]).
Verifies strict LLM prose vs. deterministic data/table/chart isolation,
Matplotlib CID PNG generation, empty Sunday scaffold guard, and SQLite subscriber lifecycle.
"""

import tempfile
import unittest
from pathlib import Path

from newsletter_content import (
    ArchiveEdition,
    NewsletterContentEngine,
    deduplicate_latest_per_day,
    enforce_sentence_limit,
    select_three_least_similar_hypotheticals,
    split_sentences,
)
from newsletter_engine import (
    ChartImageBlock,
    DataTableBlock,
    MetricItem,
    MetricStripBlock,
    NewsletterBuilder,
    SubscriberManager,
    TextSectionBlock,
    WorldMapTelemetryBlock,
    build_weekly_recap_edition,
    build_weekly_recap_scaffold,
    build_welcome_email,
    has_scaffold_placeholders,
    normalize_email,
    run_weekly_dispatch,
    sanitize_llm_prose,
)


class TestNewsletterIsolationAndEngine(unittest.TestCase):
    def test_llm_prose_sanitization_strips_html_and_escapes_entities(self):
        raw_llm = (
            "```html\n"
            "<script>evil()</script><table><tr><td>Unclosed table injection!\n"
            "Paragraph 1 with <b>tags</b> & raw symbols: x < 10 && y > 5.\n\n"
            "</div>Paragraph 2 with \"quotes\" and 'apostrophes'.\n"
            "```"
        )
        paras = sanitize_llm_prose(raw_llm)
        self.assertEqual(len(paras), 2)
        for p in paras:
            self.assertNotIn("<script>", p)
            self.assertNotIn("<table>", p)
            self.assertNotIn("</div>", p)
            self.assertNotIn("<b>", p)
        self.assertIn("x &lt; 10 &amp;&amp; y &gt; 5", paras[0])
        self.assertIn("&quot;quotes&quot;", paras[1])

    def test_strict_block_type_enforcement(self):
        builder = NewsletterBuilder(
            subject="Test Subject",
            edition_label="EDITION TEST",
        )
        with self.assertRaises(TypeError):
            builder.add_block("raw string should be rejected")  # type: ignore

    def test_data_table_and_metric_strip_isolation_from_prose(self):
        builder = NewsletterBuilder(
            subject="Isolation Verification",
            edition_label="SUNDAY RECAP",
        )
        builder.add_block(
            TextSectionBlock(
                section_id="intro",
                kicker="WRITTEN SYNTHESIS",
                heading="Grid Overview",
                paragraphs=[
                    "<table><tr><td>Attempted table breakout from LLM prose</td></tr></table> "
                    "ERCOT demand reached 81.4 GW while solar additions rose >18% YoY."
                ],
            )
        )
        builder.add_block(
            MetricStripBlock(
                block_id="kpis",
                title="KEY METRICS",
                metrics=[
                    MetricItem(label="ERCOT Peak", value="81.4 GW", delta="+4.2% WoW", trend="up"),
                    MetricItem(label="Reserve Margin", value="14.8%", delta="-0.6%", trend="down"),
                ],
            )
        )
        builder.add_block(
            DataTableBlock(
                table_id="grid_ledger",
                title="Regional Load & Generation",
                columns=["Region", "Peak Load (GW)", "YoY Delta"],
                rows=[
                    ["ERCOT", "81.4", "+4.2%"],
                    ["PJM", "142.1", "+2.9%"],
                ],
                footnote="Source: EIA & ISO telemetry.",
            )
        )

        html_out, text_out, attachments = builder.render(unsubscribe_email="reader@example.com")
        self.assertEqual(len(attachments), 0)
        # Ensure LLM prose table tag was stripped and did not inject an unstyled <td>
        self.assertNotIn("<td>Attempted table breakout from LLM prose</td>", html_out)
        self.assertIn("Attempted table breakout from LLM prose", html_out)
        self.assertIn("&gt;18% YoY", html_out)
        # Ensure deterministic table & metrics rendered properly with right-aligned numeric columns
        self.assertIn("81.4 GW", html_out)
        self.assertIn("142.1", html_out)
        self.assertIn('align="right"', html_out)
        self.assertIn("ERCOT Peak: 81.4 GW (+4.2% WoW)", text_out)

    def test_chart_image_block_compiles_png_and_attaches_cid(self):
        chart = ChartImageBlock(
            chart_id="ercot_weekly_load",
            title="ERCOT 7-Day Peak Load (GW)",
            chart_type="line",
            labels=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
            series=[{"name": "Peak GW", "values": [76.2, 78.0, 79.5, 81.4, 80.1, 75.8, 74.9]}],
            y_label="Gigawatts (GW)",
            caption="7-day peak load trajectory across ERCOT.",
        )
        builder = NewsletterBuilder(
            subject="Chart CID Test",
            edition_label="TELEMETRY EDITION",
        ).add_block(chart)

        msg = builder.to_email_message(recipient_email="subscriber@example.com")
        raw_bytes = msg.as_bytes()
        html_part = msg.get_body(preferencelist=("html",))
        self.assertIn(b"Content-ID: <ercot_weekly_load@thenewworldgrid.com>", raw_bytes)
        self.assertIn('src="cid:ercot_weekly_load@thenewworldgrid.com"', html_part.get_content())
        self.assertIsNotNone(chart.png_bytes)
        self.assertTrue(chart.png_bytes.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_weekly_recap_scaffold_is_empty_and_guarded(self):
        scaffold = build_weekly_recap_scaffold()
        self.assertTrue(has_scaffold_placeholders(scaffold))
        self.assertEqual(len(scaffold.blocks), 7)

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_subs.db"
            mgr = SubscriberManager(db_path=db_path)
            mgr.upsert_subscriber("alice@example.com", source="test", status="active")
            res = run_weekly_dispatch(manager=mgr, builder=scaffold, allow_scaffold=False)
            self.assertEqual(res["status"], "SCAFFOLD_PAUSED")
            self.assertTrue(Path(res["preview_path"]).exists())

    def test_same_day_archive_deduplication_and_three_least_similar_selection(self):
        ed_early = ArchiveEdition(
            channel="frontier",
            date_str="2026-11-05",
            timestamp_sort_key="2026-11-05T08:00_1",
            title="Early Run",
            author="ARC",
            summary_lede="Early",
            body_text="Early body",
            thought_experiment="Quantum satellites in orbit hijacked by cyber actors.",
            file_path="early.md",
        )
        ed_late = ArchiveEdition(
            channel="frontier",
            date_str="2026-11-05",
            timestamp_sort_key="2026-11-05T19:20_2",
            title="Late Run",
            author="ARC",
            summary_lede="Late",
            body_text="Late body",
            thought_experiment="Orbital debris recycling consortium monopolizes rare metals in cislunar space.",
            file_path="late.md",
        )
        deduped = deduplicate_latest_per_day([ed_early, ed_late], max_days=7)
        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0].title, "Late Run")

        # 5 hypotheticals: 3 nearly identical about quantum satellite hacking, 1 about debris mining, 1 about oceanic thermal batteries
        h_dup1 = ArchiveEdition("frontier", "2026-11-01", "1", "T1", "ARC", "", "", "Quantum communication satellite constellation hijacked by rival hackers causing encryption blackout.", "1")
        h_dup2 = ArchiveEdition("frontier", "2026-11-02", "2", "T2", "ARC", "", "", "Quantum communication satellite constellation hijacked by rival cyber hackers causing encryption crisis.", "2")
        h_dup3 = ArchiveEdition("frontier", "2026-11-03", "3", "T3", "ARC", "", "", "Quantum communication satellite network hijacked by hackers causing global encryption blackout.", "3")
        h_debris = ArchiveEdition("frontier", "2026-11-04", "4", "T4", "ARC", "", "", "Shadowy consortium monopolizes orbital debris smelting and titanium recycling in geostationary orbit.", "4")
        h_ocean = ArchiveEdition("frontier", "2026-11-05", "5", "T5", "ARC", "", "", "Autonomous deep-sea volcanic cement foundries power submarine HVDC grid cables across the Pacific.", "5")

        picked = select_three_least_similar_hypotheticals([h_dup1, h_dup2, h_dup3, h_debris, h_ocean], count=3)
        self.assertEqual(len(picked), 3)
        picked_titles = {p.title for p in picked}
        self.assertIn("T4", picked_titles)
        self.assertIn("T5", picked_titles)
        # Only 1 of the 3 repetitive quantum scenarios should be chosen
        self.assertEqual(len(picked_titles & {"T1", "T2", "T3"}), 1)

    def test_weekly_recap_edition_4_stage_synthesis_and_sentence_caps(self):
        # Use deterministic fallback (llm_fn returning None) + no external network wait
        builder = build_weekly_recap_edition(llm_fn=lambda _: None, fetch_network=False)
        self.assertEqual(len(builder.blocks), 7)

        hook_block = builder.blocks[0]
        real_block = builder.blocks[1]
        real_data_slot = builder.blocks[2]
        markets_block = builder.blocks[3]
        markets_chart_slot = builder.blocks[4]
        horizon_block = builder.blocks[5]
        horizon_visual_slot = builder.blocks[6]

        # Verify 2-sentence cap on introductory byline hook
        self.assertIsInstance(hook_block, TextSectionBlock)
        self.assertTrue(hook_block.is_byline)
        hook_sentences = split_sentences(hook_block.paragraphs[0])
        self.assertLessEqual(len(hook_sentences), 2)
        self.assertGreaterEqual(len(hook_sentences), 1)

        # Verify <= 8 sentence cap on all 3 body sections
        for blk in (real_block, markets_block, horizon_block):
            self.assertIsInstance(blk, TextSectionBlock)
            self.assertFalse(blk.is_placeholder)
            sents = split_sentences(" ".join(blk.paragraphs))
            self.assertLessEqual(len(sents), 8)
            self.assertGreaterEqual(len(sents), 2)

        # Verify mandatory opening sentence on 'On the Horizon'
        horizon_text = horizon_block.paragraphs[0]
        self.assertTrue(
            horizon_text.startswith("This week our Final Frontier author ARC posed three hypotheticals, in which"),
            f"Unexpected opening: {horizon_text}",
        )

        # Verify Data Element #1 ('The Real' World Map + 4-row HTML telemetry strip) is live & populated
        self.assertIsInstance(real_data_slot, WorldMapTelemetryBlock)
        self.assertFalse(real_data_slot.is_placeholder)
        self.assertEqual(len(real_data_slot.nodes), 4)
        self.assertEqual(len(real_data_slot.strip_rows), 4)
        html_out, text_out, attachments = builder.render(unsubscribe_email="reader@example.com")
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].chart_id, "the_real_grid_capacity_slot@thenewworldgrid.com")
        self.assertTrue(attachments[0].png_bytes.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertIn("China", html_out)
        self.assertIn("Europe (EU)", html_out)
        self.assertIn("United States", html_out)
        self.assertIn("Russia", html_out)
        self.assertIn("POWER BLOC", html_out)
        self.assertIn("EXISTING GRID", html_out)
        self.assertIn("NEW POWER BUILDOUT", html_out)

        # Verify remaining 2 paired chart/visual slots remain in placeholder mode until built
        self.assertTrue(markets_chart_slot.is_placeholder)
        self.assertTrue(horizon_visual_slot.is_placeholder)

    def test_subscriber_sqlite_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_subs.db"
            mgr = SubscriberManager(db_path=db_path)

            # 1. Add new subscriber
            is_new, row = mgr.upsert_subscriber("  Test.User@Example.com ", source="web_form")
            self.assertTrue(is_new)
            self.assertEqual(row["email"], "test.user@example.com")
            self.assertEqual(row["welcome_sent"], 0)

            # 2. Duplicate add does not re-trigger is_new
            is_new_dup, _ = mgr.upsert_subscriber("test.user@example.com", source="web_form")
            self.assertFalse(is_new_dup)

            # 3. Mark welcome sent
            mgr.mark_welcome_sent("test.user@example.com")
            self.assertEqual(len(mgr.get_pending_welcome_subscribers()), 0)

            # 4. Unsubscribe
            self.assertTrue(mgr.mark_unsubscribed("test.user@example.com"))
            self.assertEqual(len(mgr.get_active_subscribers()), 0)

            # 5. Re-subscribe reactivates
            is_reactivated, _ = mgr.upsert_subscriber("test.user@example.com", source="imap_email", status="active")
            self.assertTrue(is_reactivated)
            self.assertEqual(len(mgr.get_active_subscribers()), 1)

    def test_welcome_email_builds_cleanly(self):
        welcome = build_welcome_email()
        self.assertFalse(has_scaffold_placeholders(welcome))
        msg = welcome.to_email_message("newreader@example.com")
        self.assertIn("Welcome to The New World Grid", msg["Subject"])
        self.assertEqual(normalize_email(msg["From"]), "thenewworldgrid@gmail.com")


if __name__ == "__main__":
    unittest.main()
