import logging


def setup_logging(level: int = logging.INFO):
    """
    Setup basic logging cfg
    :return:
    """
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s][%(name)s][%(module)s] %(message)s",
    )
