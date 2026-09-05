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
        self.assertIn("class=\"nav-icon\"", content)
        self.assertIn("id=\"logout-button\"", content)
        self.assertIn('class="logout-icon"', content)
        self.assertIn("<svg viewBox=\"0 0 24 24\"", content)
        self.assertIn('class="auth-layout hidden"', content)
        self.assertIn('id="nav-back"', content)

    def test_secondary_pages_have_mobile_navigation_and_logout(self):
        for path in ("/goals/", "/commitments/"):
            with self.subTest(path=path):
                response = self.client.get(path)

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'name="viewport"')
                self.assertContains(response, "fonts.googleapis.com/css2?family=Poppins")
                self.assertContains(response, "@media (max-width: 560px)")
                self.assertContains(response, 'id="logout-button"')
                self.assertContains(response, 'class="nav-icon"')
                self.assertContains(response, 'class="logout-icon"')
                self.assertContains(response, "<svg viewBox=\"0 0 24 24\"", html=False)
                self.assertContains(response, 'id="page-menu-toggle"')
                self.assertContains(response, 'aria-controls="page-links"')
                self.assertContains(response, 'sessionStorage.removeItem("jengaAccessToken")')
                self.assertContains(response, 'sessionStorage.removeItem("jengaRefreshToken")')

    def test_how_it_works_page_is_responsive_and_links_to_signup(self):
        response = self.client.get("/how-it-works/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "How it works")
        self.assertContains(response, 'name="viewport"')
        self.assertContains(response, "fonts.googleapis.com/css2?family=Poppins")
        self.assertContains(response, "@media (max-width: 680px)")
        self.assertContains(response, "href=\"/?start=signup\"")

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
