from django.http import JsonResponse


def server_error(request):
    """Generic JSON 500, used as `handler500` and by `ExceptionMiddleware`.

    Never include the traceback, the exception text, or any internal detail in the body.
    """
    return JsonResponse({"detail": "Internal server error."}, status=500)
