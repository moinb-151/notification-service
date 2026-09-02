import logging


class ExtraFormatter(logging.Formatter):

    STANDARD_FIELDS = {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "asctime",
    }

    def format(self, record):
        message = super().format(record)

        extra = {
            key: value
            for key, value in record.__dict__.items()
            if key not in self.STANDARD_FIELDS
        }

        if extra:
            metadata = " ".join(
                f"{key}={value}"
                for key, value in extra.items()
            )

            return f"{message} | {metadata}"

        return message