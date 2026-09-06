from django.test import SimpleTestCase


class ResponsivePageContractTests(SimpleTestCase):
    def test_landing_page_has_responsive_fintech_shell(self):
        response = self.client.get("/")
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="viewport"')
        self.assertContains(response, "fonts.googleapis.com/css2?family=Poppins")
        self.assertContains(response, "@media (max-width: 760px)")
        self.assertContains(response, 'id="dashboard-menu-toggle"')
        self.assertContains(response, 'aria-controls="dashboard-links"')
        self.assertIn(".menu-toggle { display: none;", content)
        self.assertContains(response, "@media (prefers-reduced-motion: reduce)")
        self.assertContains(response, "@media (max-width: 760px)")
        self.assertIn("class=\"hero-visual\"", content)
        self.assertIn("class=\"character\"", content)
        self.assertNotIn('class="nav-icon"', content)
        self.assertIn("id=\"logout-button\"", content)
        self.assertIn('class="logout-icon"', content)
        self.assertIn('class="auth-layout hidden"', content)
        self.assertIn('id="nav-back"', content)

    def test_secondary_pages_have_mobile_navigation_and_logout(self):
        for path in ("/goals/", "/profile/"):
            with self.subTest(path=path):
                response = self.client.get(path)

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'name="viewport"')
                self.assertContains(response, "fonts.googleapis.com/css2?family=Poppins")
                self.assertContains(response, "@media (max-width: 560px)")
                self.assertContains(response, 'id="logout-button"')
                self.assertNotContains(response, 'class="nav-icon"')
                self.assertContains(response, 'class="logout-icon"')
                self.assertContains(response, 'id="page-menu-toggle"')
                self.assertContains(response, 'aria-controls="page-links"')
                self.assertContains(response, 'sessionStorage.removeItem("jengaAccessToken")')
                self.assertContains(response, 'sessionStorage.removeItem("jengaRefreshToken")')

    def test_how_it_works_page_is_responsive_and_links_to_signup(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "How it works")
        self.assertContains(response, 'name="viewport"')
        self.assertContains(response, "@media (max-width: 680px)")
        self.assertContains(response, 'id="how-it-works"')
        self.assertContains(response, "fonts.googleapis.com/css2?family=Poppins")

    def test_profile_page_has_account_layout_and_safe_mobile_navigation(self):
        response = self.client.get("/profile/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="viewport"')
        self.assertContains(response, "fonts.googleapis.com/css2?family=Poppins")
        self.assertContains(response, "Account details")
        self.assertContains(response, "Business rhythm")
        self.assertContains(response, "@media (max-width: 560px)")
        self.assertContains(response, 'aria-label="Log out"')
        self.assertContains(response, 'id="page-menu-toggle"')
        self.assertContains(response, 'id="page-links"')

    def test_landing_page_handles_an_extreme_query_string(self):
        response = self.client.get("/?next=" + ("x" * 4000))

        self.assertEqual(response.status_code, 200)

    def test_quick_actions_focus_on_decisions_not_recording(self):
        response = self.client.get("/")
        content = response.content.decode()

        quick_actions = content.split('data-i18n="quick_actions"', 1)[1].split(
            '</section>', 1
        )[0]
        self.assertNotIn('data-record="income"', quick_actions)
        self.assertNotIn('data-record="expense"', quick_actions)
        self.assertIn('id="open-afford"', quick_actions)
        self.assertIn('id="open-allocate"', quick_actions)
        self.assertIn(".spend-card .amount.large { font-size: 1.35rem; }", content)

    def test_dashboard_keeps_assistant_out_of_finance_workspace(self):
        response = self.client.get("/")
        content = response.content.decode()

        self.assertNotIn('id="ask-form"', content)
        self.assertNotIn('class="assistant-chip"', content)

    def test_assistant_page_has_plain_language_quick_prompts(self):
        response = self.client.get("/assistant/")
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn('data-chat-prompt="How am I doing with my money?"', content)
        self.assertIn('data-chat-prompt="How much can I save?"', content)
        self.assertIn('data-chat-prompt="What did I spend this week?"', content)
        self.assertIn('data-chat-prompt="Can I afford this?"', content)


class AuthenticationUIRegressionTests(SimpleTestCase):
    def test_rendered_authentication_controls_work(self):
        import json
        import re
        import shutil
        import subprocess
        from html.parser import HTMLParser
        from pathlib import Path

        if not shutil.which("node"):
            self.skipTest("Node.js is required for the JavaScript interaction check")

        class Elements(HTMLParser):
            def __init__(self):
                super().__init__()
                self.elements = []

            def handle_starttag(self, tag, attrs):
                self.elements.append(dict(attrs))

        html = self.client.get("/").content.decode()
        parser = Elements()
        parser.feed(html)
        script = next(
            block
            for block in re.findall(r"<script[^>]*>(.*?)</script>", html, re.S)
            if "function showDashboard" in block
        )
        result = subprocess.run(
            ["node", str(Path(__file__).with_name("auth_ui_check.cjs"))],
            input=json.dumps({"script": script, "elements": parser.elements}),
            text=True, capture_output=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        signup = subprocess.run(
            ["node", str(Path(__file__).with_name("auth_ui_check.cjs"))],
            input=json.dumps({"script": script, "elements": parser.elements, "entry": "signup"}),
            text=True, capture_output=True, timeout=20,
        )
        self.assertEqual(signup.returncode, 0, signup.stderr)


class NavigationUpdateTests(SimpleTestCase):
    def test_partnerships_page_and_removed_commitments_navigation(self):
        for path in ("/", "/profile/", "/goals/", "/partnerships/"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'href="/partners/"' if path in ("/profile/", "/goals/") else 'href="/partnerships/"')
            self.assertNotContains(response, 'href="/commitments/"')
            self.assertNotContains(response, "Why Jenga")
        partners = self.client.get("/partnerships/")
        self.assertContains(partners, "For SACCOs")
        self.assertContains(partners, "For banks")
        self.assertContains(partners, "No confirmed institutions are listed yet.")
        self.assertEqual(self.client.get("/commitments/").status_code, 404)

    def test_old_how_it_works_url_redirects_to_landing_section(self):
        self.assertRedirects(self.client.get("/how-it-works/"), "/#how-it-works", fetch_redirect_response=False)


class WorkspacePageTests(SimpleTestCase):
    def test_chat_is_separate_from_dashboard(self):
        home = self.client.get("/")
        self.assertNotContains(home, 'id="ask-form"')
        self.assertContains(home, 'id="summary-income"')
        self.assertContains(home, 'href="/assistant/"')
        chat = self.client.get("/assistant/")
        self.assertContains(chat, 'id="chat-form"')
        self.assertNotContains(chat, 'id="summary-income"')

    def test_savings_form_is_a_closed_dialog_initially(self):
        page = self.client.get("/goals/")
        self.assertContains(page, 'id="savings-total"')
        self.assertContains(page, 'id="open-goal"')
        self.assertContains(page, 'class="overlay hidden" id="goal-overlay"')
        self.assertContains(page, 'aria-label="Close add goal form"')

    def test_public_collaboration_and_private_accounts_are_separate(self):
        public = self.client.get("/partnerships/")
        self.assertContains(public, 'href="/signup/"')
        self.assertContains(public, "Partner with Jenga")
        self.assertNotContains(public, 'id="logout-button"')
        private = self.client.get("/partners/")
        self.assertContains(private, 'href="/partners/"')
        self.assertContains(private, 'data-i18n="nav_partners"')
        self.assertContains(private, 'id="partner-accounts"')
        self.assertContains(private, 'id="logout-button"')
        self.assertEqual(self.client.get("/signup/").status_code, 200)
