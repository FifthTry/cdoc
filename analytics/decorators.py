import time

from .models import Activity
from .events import EKind, OKind


def eval_if_function(variable, payload):
    if callable(variable):
        resp = variable(*payload)
    else:
        resp = variable
    return resp


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0]
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip


def log_http_event(oid, o_kind=None, e_kind=None, okind_ekind=None):
    def decorator(function):
        def wrapper(view, request, *args, **kwargs):
            # assert False, (type(request), type(a))
            # if callable(okind):
            #     okind = okind(request, args, kwargs)
            # if callable(okind):
            #     okind_val = okind(view, request, args, kwargs)
            # else:
            #     okind_val = okind
            if okind_ekind is not None and (o_kind is None and e_kind is None):
                if type(okind_ekind) is tuple:
                    (okind, ekind) = okind_ekind
                else:
                    # assert False, [view, request, args, kwargs]
                    (okind, ekind) = eval_if_function(
                        okind_ekind, [view, request, args, kwargs]
                    )
            else:
                okind = o_kind
                ekind = e_kind
            # if okind_ekind is None:
            okind_val = eval_if_function(okind, [view, request, args, kwargs])
            ekind_val = eval_if_function(ekind, [view, request, args, kwargs])

            oid_val = eval_if_function(oid, [view, request, args, kwargs])
            assert type(okind_val) is OKind, "Panic! Unknown Okind"
            assert type(ekind_val) is EKind, "Panic! Unknown EKind"
            activity_instance = Activity(
                url=request.get_full_path(),
                method=request.method,
                ua=request.headers.get("User-Agent"),
                ip=get_client_ip(request),
                okind=okind_val.value,
                oid=oid_val,
                ekind=ekind_val.value,
                # data={},
                site_version="",
                uid=request.user.id if request.user.is_authenticated else None,
                utm_source=request.GET.get("utm_source"),
                utm_medium=request.GET.get("utm_medium"),
                utm_campaign=request.GET.get("utm_campaign"),
                utm_term=request.GET.get("utm_term"),
                utm_content=request.GET.get("utm_content"),
            )
            start_time = time.process_time_ns()
            response = function(view, request, *args, **kwargs)
            activity_instance.duration = time.process_time_ns() - start_time

            # if response.headers["Content-Type"].lower() == "application/json":
            #     activity_instance.response = response.content
            # else:
            #     activity_instance.outcome = response.content
            activity_instance.code = response.status_code
            activity_instance.save()
            return response

        return wrapper

    return decorator
