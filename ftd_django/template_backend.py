from django.template.backends.base import BaseEngine
from django.template.backends.utils import csrf_input_lazy, csrf_token_lazy
import ftd_django.template_library
import errno
import os

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
        # self.engine = Engine(self.dirs, self.app_dirs, **options)

    def from_string(self, template_code):
        path = "templates/" + template_code
        if not os.path.exists(path):
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), path)
        return Template(path)
        # TODO:
        # try:
        #     return Template(self.engine.from_string(template_code))
        # except self.template_library.TemplateCompilationFailed as exc:
        #     raise TemplateSyntaxError(exc.args)

    def get_template(self, template_name):
        path = "templates/" + template_name
        if not os.path.exists(path):
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), path)
        return Template(path)


class Template:
    def __init__(self, template):
        self.template = template

    def render(self, context=None, request=None):
        from django.http import HttpResponse

        if context is None:
            context = {}
        if request is not None:
            context["request"] = request
            context["csrf_input"] = csrf_input_lazy(request)
            context["csrf_token"] = csrf_token_lazy(request)
        dir_path, document_id = os.path.split(self.template)
        ftd_django.template_library.ftd_build(dir_path, document_id)
        doc_id = dir_path + "/.build/"
        if document_id == "index.ftd":
            doc_id += "index.html"
        elif document_id == "FPM.ftd":
            doc_id += "-/index.html"
        else:
            doc_id += document_id.replace(".ftd", "/index.html")

        f = open(doc_id)
        return HttpResponse(f.read(), content_type="text/html")

        # return self.template.render(context)
