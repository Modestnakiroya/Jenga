from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.accounts.forms import AccountCreationForm
from apps.accounts.models import User, BusinessProfile
from apps.insights.models import Bank, Sacco, SaccoAccess, SaccoMembership, BankAccess, BankMembership


class ManagedUserForm(AccountCreationForm):
    role = forms.ChoiceField(choices=[("member", "Member"), ("sacco", "SACCO representative"), ("bank", "Bank representative"), ("admin", "Administrator")])
    sacco = forms.ModelChoiceField(queryset=Sacco.objects.order_by("name"), required=False, label="SACCO", help_text="Required for representatives; optional membership for members.")

    bank = forms.ModelChoiceField(queryset=Bank.objects.order_by("name"), required=False, label="Bank")

    def clean_phone_number(self):
        from apps.accounts.phones import normalize_phone_number
        phone = normalize_phone_number(self.cleaned_data["phone_number"])
        if User.objects.filter(phone_number=phone).exists():
            raise forms.ValidationError("This phone number already has an account.")
        return phone

    def clean(self):
        data = super().clean()
        if data.get("role") == "sacco" and not data.get("sacco"):
            self.add_error("sacco", "Choose the SACCO this representative can access.")
        if data.get("role") == "bank" and not data.get("bank"):
            self.add_error("bank", "Choose the bank this representative can access.")
        if data.get("role") == "bank" and data.get("sacco"):
            self.add_error("sacco", "Choose only a bank for a bank representative.")
        if data.get("role") in ("admin", "sacco") and data.get("bank"):
            self.add_error("bank", "Leave bank empty for this role.")
        if data.get("role") == "admin" and data.get("sacco"):
            self.add_error("sacco", "Leave SACCO empty for an administrator.")
        return data

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_superuser = user.is_staff = self.cleaned_data["role"] == "admin"
        user.save()
        BusinessProfile.objects.create(user=user, business_name=user.full_name, business_type="other")
        sacco = self.cleaned_data.get("sacco")
        if self.cleaned_data["role"] == "sacco":
            SaccoAccess.objects.create(user=user, sacco=sacco)
        elif sacco:
            SaccoMembership.objects.create(user=user, sacco=sacco)
        bank = self.cleaned_data.get("bank")
        if self.cleaned_data["role"] == "bank":
            BankAccess.objects.create(user=user, bank=bank)
        elif bank:
            BankMembership.objects.create(user=user, bank=bank)
        return user


class InstitutionForm(forms.Form):
    name = forms.CharField(max_length=180, label="Institution name")
    kind = forms.ChoiceField(choices=[("sacco", "SACCO"), ("bank", "Bank")], label="Type")

    def clean(self):
        data = super().clean()
        model = Sacco if data.get("kind") == "sacco" else Bank
        if data.get("name") and model.objects.filter(name__iexact=data["name"]).exists():
            self.add_error("name", "This institution already exists.")
        return data


class AccessForm(forms.Form):
    user = forms.ModelChoiceField(queryset=User.objects.filter(is_superuser=False).order_by("full_name"))
    sacco = forms.ModelChoiceField(queryset=Sacco.objects.order_by("name"), required=False)
    bank = forms.ModelChoiceField(queryset=Bank.objects.order_by("name"), required=False)
    purpose = forms.ChoiceField(choices=[("representative", "SACCO login access"), ("member", "Member's SACCO"), ("bank_representative", "Bank login access"), ("bank_member", "Member's bank")])

    def clean(self):
        data = super().clean()
        is_bank = data.get("purpose", "").startswith("bank_")
        wrong_field = "sacco" if is_bank else "bank"
        if data.get(wrong_field):
            self.add_error(wrong_field, "Leave this field empty for the selected assignment type.")
        return data


@user_passes_test(lambda user: user.is_active and user.is_superuser, login_url="/admin/login/")
@require_http_methods(["GET", "POST"])
def workspace(request):
    user_form, institution_form, access_form = ManagedUserForm(), InstitutionForm(), AccessForm()
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add_user":
            user_form = ManagedUserForm(request.POST)
            if user_form.is_valid():
                user_form.save()
                messages.success(request, "User added. They can sign in with the phone number and password you set.")
                return redirect("admin-workspace")
        elif action == "add_institution":
            institution_form = InstitutionForm(request.POST)
            if institution_form.is_valid():
                model = Sacco if institution_form.cleaned_data["kind"] == "sacco" else Bank
                model.objects.create(name=institution_form.cleaned_data["name"])
                messages.success(request, "Institution added. To give it login access, add a representative below and select this institution.")
                return redirect("admin-workspace")
        elif action == "access":
            access_form = AccessForm(request.POST)
            if access_form.is_valid():
                data = access_form.cleaned_data
                is_bank = data["purpose"].startswith("bank_")
                representative = data["purpose"] in ("representative", "bank_representative")
                model = (BankAccess if representative else BankMembership) if is_bank else (SaccoAccess if representative else SaccoMembership)
                field = "bank" if is_bank else "sacco"
                with transaction.atomic():
                    if data[field]:
                        defaults = {field: data[field]}
                        if representative:
                            defaults["is_active"] = True
                            (SaccoAccess if is_bank else BankAccess).objects.filter(user=data["user"]).delete()
                        model.objects.update_or_create(user=data["user"], defaults=defaults)
                    else:
                        model.objects.filter(user=data["user"]).delete()
                messages.success(request, "Institution assignment updated.")
                return redirect("admin-workspace")
        elif action == "delete_user":
            target = get_object_or_404(User, pk=request.POST.get("user_id"))
            if target.pk == request.user.pk:
                messages.error(request, "You cannot delete your own administrator account.")
            elif request.POST.get("confirm") == "yes":
                with transaction.atomic():
                    target.delete()
                messages.success(request, "User and their associated records deleted.")
            else:
                return render(request, "admin_workspace.html", {"delete_target": target})
            return redirect("admin-workspace")
    users = User.objects.select_related("sacco_access__sacco", "bank_access__bank").order_by("full_name", "phone_number")
    query = request.GET.get("q", "").strip()
    if query:
        from django.db.models import Q
        users = users.filter(Q(full_name__icontains=query) | Q(phone_number__icontains=query))
    from django.core.paginator import Paginator
    return render(request, "admin_workspace.html", {
        "user_form": user_form, "institution_form": institution_form, "access_form": access_form,
        "users": Paginator(users, 25).get_page(request.GET.get("page")), "query": query,
        "saccos": Sacco.objects.order_by("name"), "banks": Bank.objects.order_by("name"),
    })
