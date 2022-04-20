"""cdoc URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
import ftd_django
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.shortcuts import render
from django.contrib.auth import views as auth_views
from django.views.generic import TemplateView

import glob

from app import views as app_views

urlpatterns = [
    path(
        "accounts/login/",
        app_views.LoginView.as_view(),
    ),
    path(
        "accounts/logout/",
        auth_views.LogoutView.as_view(next_page="/"),
    ),
    path(
        "<str:account_name>/repos/",
        app_views.ListInstallationRepos.as_view(),
    ),
    path(
        "<str:account_name>/<str:repo_name>/pull/<int:pr_number>/",
        app_views.PRView.as_view(),
    ),
    path(
        "<str:account_name>/<str:repo_name>/pulls/",
        app_views.AllPRView.as_view(),
    ),
    #
    path("app/", include("app.urls")),
    path("admin/", admin.site.urls),
    path(
        "",
        TemplateView.as_view(template_name="index.html"),
    ),
    path("ftd/", app_views.IndexView.as_view()),
] + ftd_django.static()


def make_v(template, context):
    def v(request):
        return render(request, template, context=context)

    return v


def s(p, **data):
    import json

    d = json.load(open(p))

    p = p.replace("samples/", "").replace(".json", "")
    print(p, d)

    return (
        path("samples/" + ("" if p == "index" else p + "/"), make_v(d["template"], d)),
        p,
        d,
    )


if settings.DEBUG:
    d = [s(f) for f in glob.glob("samples/**/*.json", recursive=True)]

    urlpatterns.append(path("samples/", make_v("samples.html", context={"data": d})))

    urlpatterns += [i[0] for i in d]
