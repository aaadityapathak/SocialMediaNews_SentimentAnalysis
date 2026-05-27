import time
from valkey import Valkey


def wait_queue(
    poll_interval: int = 6, silent: bool = False, until_length: int = 0
):
    """
    Wait for the queue to finish processing
    :return:
    """
    vk = Valkey()
    until_length = max(0, until_length)

    while total := vk.llen("social-posts-index"):
        err_len = vk.llen("process-errors")
        if not silent:
            print("Remaining: %5d Errors: %d" % (total, err_len))

        if total <= until_length:
            break
        time.sleep(poll_interval)


if __name__ == "__main__":
    import fire

    fire.Fire(wait_queue)
