import asyncio
import ftd
from django.template import Library, TemplateDoesNotExist, TemplateSyntaxError
from django.template.backends.base import BaseEngine
from django.template.backends.utils import csrf_input_lazy, csrf_token_lazy
from django.template.engine import Engine

from django.conf import settings


class FTDTemplateBackend(BaseEngine):

    # Name of the subdirectory containing the templates for this engine
    # inside an installed application.
    app_dirname = "templates"

    def __init__(self, params):
        params = params.copy()
        options = params.pop("OPTIONS").copy()
        options.setdefault("autoescape", True)
        options.setdefault("debug", settings.DEBUG)
        options.setdefault("file_charset", "utf-8")
        # libraries = options.get("libraries", {})
        # options["libraries"] = self.get_templatetag_libraries(libraries)
        super().__init__(params)
        self.engine = Engine(self.dirs, self.app_dirs, **options)

    def from_string(self, template_code):
        try:
            return Template(self.engine.from_string(template_code))
        except self.template_library.TemplateCompilationFailed as exc:
            raise TemplateSyntaxError(exc.args)

    def get_template(self, template_name):
        try:
            return Template(self.engine.get_template(template_name))
        except TemplateDoesNotExist as exc:
            raise exc


class Template:
    def __init__(self, template):
        self.template = template

    def render(self, context=None, request=None):
        if context is None:
            context = {}
        if request is not None:
            context["request"] = request
            context["csrf_input"] = csrf_input_lazy(request)
            context["csrf_token"] = csrf_token_lazy(request)
        # loop = asyncio.new_event_loop()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        resp = loop.run_until_complete(
            ftd.fpm_build(
                self.template.origin.name, self.template.origin.template_name, False
            )
        )
        # assert False, resp
        return resp

        # return self.template.render(context)
