from django.contrib.auth.models import Group, User
from django.test import TestCase, Client
from django.urls import reverse

from inspection.models import Inspection
from inspection.rules import judge


FAIL_CASES = [
    {
        "name": "光强不足",
        "measured": 800.0,
        "required": 1200.0,
        "bearing": 0.2,
        "verdict": "不合格",
        "note": "光强不足",
    },
    {
        "name": "方位越限",
        "measured": 1400.0,
        "required": 1200.0,
        "bearing": 2.5,
        "verdict": "不合格",
        "note": "方位偏差过大",
    },
    {
        "name": "两项都不满足",
        "measured": 800.0,
        "required": 1200.0,
        "bearing": -3.0,
        "verdict": "不合格",
        # 光强优先判定，判词必须仍是判定函数的原话
        "note": "光强不足",
    },
]


class JudgeTests(TestCase):
    def test_three_fail_branches_return_exact_wording(self):
        for case in FAIL_CASES:
            with self.subTest(case=case["name"]):
                self.assertEqual(
                    judge(case["measured"], case["required"], case["bearing"]),
                    (case["verdict"], case["note"]),
                )

    def test_pass_branch(self):
        self.assertEqual(judge(1400.0, 1200.0, 0.4), ("合格", "光强与方位均在限内"))


class InspectionFlowTests(TestCase):
    def setUp(self):
        inspectors = Group.objects.create(name="inspector")
        self.keeper = User.objects.create_user(username="keeper", password="light123456")
        self.keeper.groups.add(inspectors)
        self.watch = User.objects.create_user(username="watch", password="watch123456")
        self.client = Client()

    def _post(self, case, code):
        response = self.client.post(
            reverse("create"),
            {
                "aid_code": code,
                "measured_cd": case["measured"],
                "required_cd": case["required"],
                "bearing_error_deg": case["bearing"],
            },
        )
        self.assertEqual(response.status_code, 302)
        return response

    def test_failing_submissions_survive_through_save_list_and_detail(self):
        self.assertTrue(self.client.login(username="keeper", password="light123456"))
        for case in FAIL_CASES:
            with self.subTest(case=case["name"]):
                response = self._post(case, f"A-{case['name']}")

                # 1) 保存瞬间：库里就是判定函数的原话，没有任何旁路改写
                row = Inspection.objects.get(aid_code=f"A-{case['name']}")
                self.assertEqual(row.verdict, case["verdict"])
                self.assertEqual(row.note, case["note"])

                # 2) 总表：徽标颜色与结论文本对得上
                listing = self.client.get(reverse("list"))
                self.assertEqual(listing.status_code, 200)
                self.assertContains(
                    listing,
                    f'<td class="bad">{case["verdict"]}</td>',
                    html=False,
                )
                self.assertContains(listing, f"<td>{case['note']}</td>")
                self.assertNotContains(listing, '<td class="ok">不合格</td>')

                # 3) 详情：附言同样是判定函数的原话，颜色一致
                detail = self.client.get(response.url)
                self.assertEqual(detail.status_code, 200)
                self.assertContains(
                    detail,
                    f'<p class="bad">{case["verdict"]} · {case["note"]}</p>',
                )
                self.assertNotContains(detail, "光强与方位均在限内")

    def test_passing_submission_is_green_everywhere(self):
        self.assertTrue(self.client.login(username="keeper", password="light123456"))
        response = self.client.post(
            reverse("create"),
            {
                "aid_code": "A-OK",
                "measured_cd": 1400.0,
                "required_cd": 1200.0,
                "bearing_error_deg": 0.4,
            },
        )
        self.assertEqual(response.status_code, 302)
        row = Inspection.objects.get(aid_code="A-OK")
        self.assertEqual((row.verdict, row.note), ("合格", "光强与方位均在限内"))

        listing = self.client.get(reverse("list"))
        self.assertContains(listing, '<td class="ok">合格</td>')

        detail = self.client.get(response.url)
        self.assertContains(detail, '<p class="ok">合格 · 光强与方位均在限内</p>')

    def test_readonly_user_cannot_write(self):
        self.assertTrue(self.client.login(username="watch", password="watch123456"))

        # 列表页不给登记入口
        listing = self.client.get(reverse("list"))
        self.assertEqual(listing.status_code, 200)
        self.assertNotContains(listing, reverse("create"))

        # GET 登记页直接拒绝
        self.assertEqual(self.client.get(reverse("create")).status_code, 403)

        # POST 被拒绝且不留任何记录
        before = Inspection.objects.count()
        forbidden = self.client.post(
            reverse("create"),
            {
                "aid_code": "A-HACK",
                "measured_cd": 800.0,
                "required_cd": 1200.0,
                "bearing_error_deg": 0.2,
            },
        )
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(Inspection.objects.count(), before)
        self.assertFalse(Inspection.objects.filter(aid_code="A-HACK").exists())

    def test_anonymous_user_cannot_write(self):
        response = self.client.post(
            reverse("create"),
            {
                "aid_code": "A-ANON",
                "measured_cd": 800.0,
                "required_cd": 1200.0,
                "bearing_error_deg": 0.2,
            },
        )
        # 未登录被重定向到登录页，而不是写入
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Inspection.objects.filter(aid_code="A-ANON").exists())
