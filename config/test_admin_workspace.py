from django.test import TestCase, override_settings, Client
from apps.accounts.models import User, BusinessProfile
from apps.insights.models import Sacco, Bank, SaccoAccess


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AdminWorkspaceTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("+256700111111", "AdminPass123!", full_name="Admin")
        self.client.force_login(self.admin)

    def payload(self, **extra):
        return {"action": "add_user", "phone_number": "0700222222", "full_name": "New Person", "password1": "NewPass456!", "password2": "NewPass456!", "role": "member", **extra}

    def test_dashboard_is_simple(self):
        response = self.client.get("/admin/")
        self.assertContains(response, "People and institutions")
        self.assertNotContains(response, "Groups")

    def test_non_admin_cannot_read_or_mutate(self):
        member = User.objects.create_user("+256700333333", "MemberPass123!")
        SaccoAccess.objects.create(user=member, sacco=Sacco.objects.create(name="Local SACCO"))
        self.client.force_login(member)
        self.assertEqual(self.client.get("/admin/").status_code, 302)
        self.assertEqual(self.client.post("/admin/", self.payload(role="admin")).status_code, 302)
        self.assertFalse(User.objects.filter(phone_number="+256700222222").exists())

    def test_create_admin_and_profile(self):
        self.assertEqual(self.client.post("/admin/", self.payload(role="admin")).status_code, 302)
        person = User.objects.get(phone_number="+256700222222")
        self.assertTrue(person.is_superuser and person.is_staff)
        self.assertTrue(person.check_password("NewPass456!"))
        self.assertTrue(BusinessProfile.objects.filter(user=person).exists())

    def test_create_representative_and_required_assignment(self):
        response = self.client.post("/admin/", self.payload(role="sacco"))
        self.assertContains(response, "Choose the SACCO")
        sacco = Sacco.objects.create(name="Members SACCO")
        self.client.post("/admin/", self.payload(role="sacco", sacco=sacco.pk))
        person = User.objects.get(phone_number="+256700222222")
        self.assertFalse(person.is_staff or person.is_superuser)
        self.assertEqual(person.sacco_access.sacco, sacco)

    def test_institutions(self):
        for kind in ("bank", "sacco"):
            self.assertEqual(self.client.post("/admin/", {"action":"add_institution", "kind":kind, "name":"Test institution"}).status_code, 302)
        self.assertEqual(Bank.objects.count(), 1)
        self.assertEqual(Sacco.objects.count(), 1)

    def test_delete_requires_confirmation_and_blocks_self_deletion(self):
        person = User.objects.create_user("+256700444444", "DeletePass123!")
        payload = {"action":"delete_user", "user_id":person.pk}
        self.assertContains(self.client.post("/admin/", payload), "This cannot be undone")
        self.assertTrue(User.objects.filter(pk=person.pk).exists())
        self.client.post("/admin/", {**payload, "confirm":"yes"})
        self.assertFalse(User.objects.filter(pk=person.pk).exists())
        self.client.post("/admin/", {"action":"delete_user", "user_id":self.admin.pk, "confirm":"yes"})
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())

    def test_csrf_required(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(client.post("/admin/", self.payload()).status_code, 403)
