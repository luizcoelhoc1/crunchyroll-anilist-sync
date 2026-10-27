import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sync_anilist as s
from test_sync import group, media, mapping

SERIES = "G12345678"


def linked(i=10, title="Example", sid=SERIES, **kwargs):
    m = media(i, title=title, **kwargs)
    m["externalLinks"] = [{"site": "Crunchyroll",
                          "url": f"https://www.crunchyroll.com/series/{sid}/example"}]
    return m


def source(season=1):
    g = group([1, 2, 3], key=SERIES + "|S1")
    g.update(series=SERIES, season=f"Season {season}", sn=season)
    return g


class ExternalLinkTests(unittest.TestCase):
    def test_series_id_ignores_locale_slug_and_query(self):
        for url in (f"https://www.crunchyroll.com/pt-br/series/{SERIES}/nome?ref=abc",
                    f"https://crunchyroll.com/series/{SERIES}/different-title",
                    f"http://www.crunchyroll.com/en/series/{SERIES.lower()}/",
                    f"https://www.crunchyroll.com:443/series/{SERIES}"):
            self.assertEqual(s.crunchyroll_series_id(url), SERIES)

    def test_false_domains_and_non_series_links_are_not_evidence(self):
        for url in (f"https://crunchyroll.com.evil.example/series/{SERIES}",
                    f"https://www.crunchyroll.com@evil.example/series/{SERIES}",
                    f"https://user@www.crunchyroll.com/series/{SERIES}",
                    f"https://www.crunchyroll.com/watch/{SERIES}",
                    f"https://www.crunchyroll.com:bad/series/{SERIES}",
                    "https://www.crunchyroll.com/example", None):
            self.assertIsNone(s.crunchyroll_series_id(url))

    def test_source_id_prefers_api_metadata_over_key(self):
        g = source()
        g["key"] = "G99999999|S1"
        self.assertEqual(s.source_series_id(g), SERIES)

    def test_matching_link_is_preferred_to_identical_title_without_link(self):
        rule, _ = s.auto_rule(source(), {20: media(20), 10: linked()})
        self.assertEqual(rule["mediaId"], 10)
        self.assertEqual(rule["evidence"]["method"], "crunchyroll_link")

    def test_identical_title_with_conflicting_link_is_rejected(self):
        rule, reason = s.auto_rule(source(), {10: linked(sid="G99999999")})
        self.assertIsNone(rule)
        self.assertIn("outra serie", reason)

    def test_no_link_uses_exact_title_fallback(self):
        rule, _ = s.auto_rule(source(), {10: media()})
        self.assertEqual(rule["evidence"]["method"], "title")

    def test_shared_franchise_link_still_selects_correct_season(self):
        first = linked(10)
        second = linked(20, title="Example Season 2")
        rule, _ = s.auto_rule(source(2), {10: first, 20: second})
        self.assertEqual(rule["mediaId"], 20)

    def test_link_allows_base_name_translation_with_explicit_season(self):
        rule, _ = s.auto_rule(source(2), {20: linked(20, title="Nome traduzido 2nd Season")})
        self.assertEqual(rule["mediaId"], 20)
        self.assertEqual(rule["evidence"]["season_check"], "explicit_season")

    def test_link_alone_cannot_infer_first_season_from_partial_catalog(self):
        rule, _ = s.auto_rule(source(), {20: linked(20, title="Other Season 2")})
        self.assertIsNone(rule)

    def test_two_linked_same_season_candidates_stay_pending(self):
        rule, reason = s.auto_rule(source(2), {10: linked(10, title="Example Season 2"),
                                             20: linked(20, title="Another name Season 2")})
        self.assertIsNone(rule)
        self.assertIn("compartilhado", reason)

    def test_unknown_linked_season_does_not_choose_wrong_part(self):
        m = linked(20, title="Example Season 2 Part 2")
        m["synonyms"] = ["Example Season 2"]
        rule, _ = s.auto_rule(source(2), {20: m})
        self.assertIsNone(rule)

    def test_explicit_part_can_disambiguate_shared_season(self):
        g = source(2)
        g["season"] = "Season 2 Part 2"
        first = linked(10, title="Example Season 2 Part 1")
        second = linked(20, title="Nome traduzido Season 2 Part 2")
        rule, _ = s.auto_rule(g, {10: first, 20: second})
        self.assertEqual(rule["mediaId"], 20)

    def test_roman_second_part_is_not_treated_as_whole_season(self):
        m = linked(20, title="Example Season 2 Part II")
        rule, _ = s.auto_rule(source(2), {20: m})
        self.assertIsNone(rule)

    def test_extra_season_subtitle_needs_exact_confirmation(self):
        m = linked(20, title="Other Season 2 The Final Chapters")
        rule, _ = s.auto_rule(source(2), {20: m})
        self.assertIsNone(rule)

    def test_link_does_not_override_cumulative_episode_check(self):
        g = source()
        g["rows"] = group([13, 14, 15])["rows"]
        rule, reason = s.auto_rule(g, {10: linked()})
        self.assertIsNone(rule)
        self.assertIn("cumulativa", reason)

    def test_link_does_not_assign_main_tv_season_to_special(self):
        g = source()
        g["sn"] = 0
        g["rows"][0]["type"] = "movie"
        rule, _ = s.auto_rule(g, {10: linked()})
        self.assertIsNone(rule)

    def test_plan_records_link_and_manual_mapping_evidence(self):
        g = source()
        catalog = {10: linked()}
        automatic = s.build_plan([g], [], catalog, {"groups": {}}, {"id": 1, "name": "demo"})
        c = automatic["changes"][0]
        self.assertEqual(s.match_label(c), "ID Crunchyroll")
        self.assertEqual(c["matches"][0]["source_series_id"], SERIES)
        self.assertIn("/series/" + SERIES, c["matches"][0]["crunchyroll_url"])
        manual = s.build_plan([g], [], catalog, mapping(key=g["key"]), {"id": 1, "name": "demo"})
        self.assertEqual(s.match_label(manual["changes"][0]), "Mapeamento")

    def test_catalog_fetches_related_anime_links_but_not_manga(self):
        first = linked()
        first["relations"] = {"edges": [
            {"relationType": "SEQUEL", "node": {"id": 20, "type": "ANIME"}},
            {"relationType": "PREQUEL", "node": {"id": 30, "type": "MANGA"}},
            {"relationType": "CHARACTER", "node": {"id": 40, "type": "ANIME"}}]}
        sequel = linked(20, title="Example Season 2")
        al = s.AniList("fake")
        al.http.log = lambda _: None
        al.gql = Mock(side_effect=[{"s0": {"media": [first]}}, {"Page": {"media": [sequel]}}])
        catalog = al.catalog([source(2)], {"groups": {}}, [])
        self.assertEqual(set(catalog), {10, 20})
        self.assertIn("externalLinks", al.gql.call_args_list[0].args[0])
        self.assertIn("relations", al.gql.call_args_list[0].args[0])
        self.assertEqual(al.gql.call_args_list[1].args[1], {"ids": [20]})
        rule, _ = s.auto_rule(source(2), catalog)
        self.assertEqual(rule["mediaId"], 20)


if __name__ == "__main__":
    unittest.main()
