from django.contrib import admin
from django import forms
from . import models


# admin.site.register(models.GithubAppAuth)
# admin.site.register(models.GithubUser)


# class GithubRepoMapAdmin(admin.TabularInline):
#     model = models.GithubRepoMap

#     def formfield_for_foreignkey(self, db_field, request, **kwargs):
#         print(db_field.name)
#         # print(request)
#         # print(kwargs)
#         if db_field.name in ["code_repo", "documentation_repo"]:
#             github_app_installation_id = request.resolver_match.kwargs.get("object_id")
#             kwargs["queryset"] = models.GithubRepository.objects.filter(
#                 owner_id=github_app_installation_id
#             )
#         return super(GithubRepoMapAdmin, self).formfield_for_foreignkey(
#             db_field, request, **kwargs
#         )

#     # def get_queryset(self, request):
#     #     qs = super(GithubRepoMapAdmin, self).get_queryset(request)
#     #     return qs.filter(=request.user)


# class GithubAppInstallationForm(forms.ModelForm):
#     class Meta:
#         model = models.GithubAppInstallation
#         exclude = ["account_id"]


# class GithubAppInstallationAdmin(admin.ModelAdmin):
#     list_display = (
#         "account_name",
#         "created_at",
#     )
#     readonly_fields = (
#         "account_name",
#         "installation_id",
#         "account_type",
#         "state",
#         "creator",
#     )

#     form = GithubAppInstallationForm
#     inlines = [
#         GithubRepoMapAdmin,
#     ]

#     def get_queryset(self, request):
#         qs = super(GithubAppInstallationAdmin, self).get_queryset(request)
#         if request.user.is_superuser:
#             return qs
#         else:
#             return qs.filter(creator=request.user.github_user)

#     def get_form(self, request, obj=None, **kwargs):
#         form = super(GithubAppInstallationAdmin, self).get_form(request, obj, **kwargs)
#         # form.base_fields['theme'].queryset = Theme.objects.filter(name__iexact='company')
#         return form


# admin.site.register(models.GithubAppInstallation, GithubAppInstallationAdmin)
# admin.site.register(models.GithubUserAccessToken)
# admin.site.register(models.GithubUserRefreshToken)
# admin.site.register(models.GithubInstallationToken)
# admin.site.register(models.GithubPullRequest)
# admin.site.register(models.MonitoredPullRequest)
# admin.site.register(models.GithubCheckRun)
# # admin.site.register(models.GithubRepoMap)
