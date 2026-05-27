from playwright_stealth import Stealth
from playwright.sync_api import sync_playwright
from parsel import Selector
import jmespath
from nested_lookup import nested_lookup
import json


def parse_thread(data):
    try:
        result = jmespath.search(
            """{
            text: post.caption.text,
            published_on: post.taken_at,
            id: post.id,
            username: post.user.username,
            user_verified: post.user.is_verified,
            reply_count: view_replies_cta_string,
            like_count: post.like_count,
            images: post.carousel_media[].image_versions2.candidates[1].url,
            videos: post.video_versions[].url
        }""",
            data,
        )
        if not result:
            return {}
        result["videos"] = list(set(result["videos"] or []))
        if result.get("reply_count") and isinstance(result["reply_count"], str):
            try:
                result["reply_count"] = int(result["reply_count"].split(" ")[0])
            except ValueError:
                result["reply_count"] = None
        if result.get("username") and data.get("post", {}).get("code"):
            result["url"] = (
                f"https://www.threads.net/@{result['username']}/post/{data['post']['code']}"
            )
        return result
    except Exception:
        return {}


def scrape_keyword(keyword: str) -> tuple[list, bool]:
    """Returns a tuple of (results: list, is_blocked: bool)"""
    results = []
    network_status = {"blocked": False, "reason": ""}

    with Stealth().use_sync(sync_playwright()) as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=[
                "--headless=new",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )

        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="Australia/Melbourne",
        )

        page = context.new_page()

        def handle_response(response):
            if response.status in [403, 429]:
                network_status["blocked"] = True
                network_status["reason"] = f"HTTP {response.status}"

        page.on("response", handle_response)

        search_url = (
            f"https://www.threads.net/search?q={keyword}&serp_type=default"
        )

        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(4000)

            # --- BLOCK DETECTION LOGIC ---
            if network_status["blocked"]:
                print(
                    f"🚨 IP BLOCKED for '{keyword}': {network_status['reason']}"
                )
                browser.close()
                return [], True  # Return blocked = True

            if "login" in page.url.lower() or "Instagram" in page.title():
                print(f"🚨 LOGIN WALL hit for '{keyword}'. IP is flagged.")
                browser.close()
                return [], True  # Return blocked = True

        except Exception as e:
            print(f"⚠️ Page load error for '{keyword}': {e}")
            browser.close()
            return [], False

        previous_height = 0
        scroll_attempts = 0
        while scroll_attempts < 2:
            page.mouse.wheel(delta_x=0, delta_y=1500)
            page.wait_for_timeout(3000)

            current_height = page.evaluate("document.body.scrollHeight")
            if current_height == previous_height:
                scroll_attempts += 1
            else:
                scroll_attempts = 0
            previous_height = current_height

        selector = Selector(page.content())
        hidden_datasets = selector.css(
            'script[type="application/json"]::text'
        ).getall()

        for hidden_dataset in hidden_datasets:
            if "thread_items" not in hidden_dataset:
                continue
            try:
                data = json.loads(hidden_dataset)
                thread_items = nested_lookup("thread_items", data)

                for thread_list in thread_items:
                    for item in thread_list:
                        parsed = parse_thread(item)
                        if parsed and parsed.get("text") and parsed.get("id"):
                            results.append(parsed)
            except Exception:
                continue

        browser.close()

    unique_results = {r["id"]: r for r in results if "id" in r}.values()
    return list(unique_results), False  # Successfully finished, not blocked
