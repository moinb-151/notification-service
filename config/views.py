from django.http import JsonResponse, StreamingHttpResponse
import asyncio


def health_check(request):
    return JsonResponse({"status": "ok"})

async def sse_probe(request):
    async def event_stream():
        yield ": probe-started\n\n"

        while True:
            await asyncio.sleep(5)
            yield ": heartbeat\n\n"

    response = StreamingHttpResponse(
        event_stream(),
        content_type="text/event-stream",
    )

    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"

    return response