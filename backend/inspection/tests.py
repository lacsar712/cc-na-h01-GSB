from django.contrib.auth.models import Group, User
from django.test import TestCase

from inspection.models import Inspection
from inspection.rules import judge


# 三种不达标工况 + 一种合格工况：(实测, 要求, 方位偏差, 期望结论, 期望附言)
CANDELA_SHORT = (800, 1200, 0.2, "不合格", "光强不足")
BEARING_OVER = (1400, 1200, 3.5, "不合格", "方位偏差过大")
BOTH_BAD = (800, 1200, 3.5, "不合格", "光强不足")
ALL_GOOD = (1400, 1200, 0.4, "合格", "光强与方位均在限内")


class JudgeTests(TestCase):
    """判定函数本身对三种工况必须给出完整原话，而不只是一个布尔位。"""

    def test_candela_short(self):
        measured, required, bearing, verdict, note = CANDELA_SHORT
        self.assertEqual(judge(measured, required, bearing), (verdict, note))

    def test_bearing_over_limit(self):
        measured, required, bearing, verdict, note = BEARING_OVER
        self.assertEqual(judge(measured, required, bearing), (verdict, note))

    def test_candela_and_bearing_both_bad(self):
        measured, required, bearing, verdict, note = BOTH_BAD
        self.assertEqual(judge(measured, required, bearing), (verdict, note))

    def test_all_good(self):
        measured, required, bearing, verdict, note = ALL_GOOD
        self.assertEqual(judge(measured, required, bearing), (verdict, note))


class InspectionFlowTests(TestCase):
    def setUp(self):
        inspectors = Group.objects.create(name="inspector")
        self.keeper = User.objects.create_user("keeper", password="light123456")
        self.keeper.groups.add(inspectors)
        self.watch = User.objects.create_user("watch", password="watch123456")

    def _post(self, case, code="LH-09"):
        measured, required, bearing, _verdict, _note = case
        return self.client.post(
            "/inspections/new/",
            {
                "aid_code": code,
                "measured_cd": measured,
                "required_cd": required,
                "bearing_error_deg": bearing,
            },
        )

    def _assert_pages_match_judge(self, case, row):
        """保存瞬间、列表颜色/说明、详情附言三处必须与 judge 原话逐字一致。"""
        _measured, _required, _bearing, verdict, note = case
        css = "ok" if verdict == "合格" else "bad"

        detail = self.client.get(f"/inspections/{row.pk}/")
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, f'<p class="{css}">{verdict} · {note}</p>', html=True)

        listing = self.client.get("/")
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, f'<td class="{css}">{verdict}</td>', html=True)
        self.assertContains(listing, f"<td>{note}</td>", html=True)

    def test_save_candela_short_uses_judge_words_everywhere(self):
        self.client.force_login(self.keeper)
        response = self._post(CANDELA_SHORT)
        self.assertEqual(response.status_code, 302)

        row = Inspection.objects.get()
        verdict, note = judge(
            row.measured_cd, row.required_cd, row.bearing_error_deg
        )
        self.assertEqual(row.verdict, verdict)
        self.assertEqual(row.note, note)
        self.assertEqual((row.verdict, row.note), ("不合格", "光强不足"))
        self._assert_pages_match_judge(CANDELA_SHORT, row)

    def test_save_bearing_over_limit_uses_judge_words_everywhere(self):
        self.client.force_login(self.keeper)
        response = self._post(BEARING_OVER, code="LH-12")
        self.assertEqual(response.status_code, 302)

        row = Inspection.objects.get()
        verdict, note = judge(
            row.measured_cd, row.required_cd, row.bearing_error_deg
        )
        self.assertEqual((row.verdict, row.note), (verdict, note))
        self.assertEqual((row.verdict, row.note), ("不合格", "方位偏差过大"))
        self._assert_pages_match_judge(BEARING_OVER, row)

    def test_save_both_bad_uses_judge_words_everywhere(self):
        self.client.force_login(self.keeper)
        response = self._post(BOTH_BAD, code="LH-13")
        self.assertEqual(response.status_code, 302)

        row = Inspection.objects.get()
        verdict, note = judge(
            row.measured_cd, row.required_cd, row.bearing_error_deg
        )
        self.assertEqual((row.verdict, row.note), (verdict, note))
        # 两项同时不满足时 judge 先报光强不足，三处都不得被改写成合格
        self.assertEqual((row.verdict, row.note), ("不合格", "光强不足"))
        self._assert_pages_match_judge(BOTH_BAD, row)

    def test_save_good_is_green(self):
        self.client.force_login(self.keeper)
        response = self._post(ALL_GOOD, code="LH-01")
        self.assertEqual(response.status_code, 302)

        row = Inspection.objects.get()
        self.assertEqual((row.verdict, row.note), ("合格", "光强与方位均在限内"))
        self._assert_pages_match_judge(ALL_GOOD, row)


class ReadOnlyAccountTests(TestCase):
    def setUp(self):
        inspectors = Group.objects.create(name="inspector")
        self.keeper = User.objects.create_user("keeper", password="light123456")
        self.keeper.groups.add(inspectors)
        self.watch = User.objects.create_user("watch", password="watch123456")
        self.payload = {
            "aid_code": "LH-09",
            "measured_cd": 800,
            "required_cd": 1200,
            "bearing_error_deg": 0.2,
        }

    def test_readonly_cannot_open_form(self):
        self.client.force_login(self.watch)
        response = self.client.get("/inspections/new/")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Inspection.objects.count(), 0)

    def test_readonly_post_is_forbidden_and_writes_nothing(self):
        self.client.force_login(self.watch)
        response = self.client.post("/inspections/new/", self.payload)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Inspection.objects.count(), 0)

    def test_anonymous_post_is_redirected_to_login(self):
        response = self.client.post("/inspections/new/", self.payload)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)
        self.assertEqual(Inspection.objects.count(), 0)

    def test_readonly_can_still_view_list_and_detail(self):
        self.client.force_login(self.keeper)
        created = self.client.post("/inspections/new/", self.payload)
        row = Inspection.objects.get()

        self.client.force_login(self.watch)
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get(f"/inspections/{row.pk}/").status_code, 200)
