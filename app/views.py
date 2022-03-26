from django.shortcuts import render
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt


@method_decorator(csrf_exempt, name='dispatch')
class AuthCallback(View):

    def get(self, request):
        print(request)
        assert False, request
        # return render(request, 'app/callback.html')


@method_decorator(csrf_exempt, name='dispatch')
class WebhookCallback(View):

    def post(self, request, *args, **kwargs):
        print(request.POST)
        print(args)
        print(kwargs)
        assert False, request.__dict__


@method_decorator(csrf_exempt, name='dispatch')
class OauthCallback(View):

    def get(self, request):
        print(request)
        assert False, request
