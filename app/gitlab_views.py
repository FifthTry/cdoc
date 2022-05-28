from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views import View
from app import models as app_models
from django.conf import settings
from requests.models import PreparedRequest
import base64
import hashlib
import requests


