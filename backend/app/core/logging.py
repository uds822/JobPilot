import logging

from app.core.request_context import request_id_context


class RequestIDFormatter(logging.Formatter):

    def format(self, record):
        request_id = request_id_context.get()

        if request_id:
            record.request_id = request_id
        else:
            record.request_id = "-"

        return super().format(record)


def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    formatter = RequestIDFormatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] "
        "[request_id=%(request_id)s] %(message)s"
    )

    if logger.handlers:
        for handler in logger.handlers:
            handler.setFormatter(formatter)
    else:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
