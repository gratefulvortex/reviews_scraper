import asyncio
import random
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

async def scrape_reviews(url):
    reviews = []
    page_num = 1

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # Non-headless for manual login
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = await context.new_page()

        try:
            # Navigate to the review page with longer timeout
            print(f"Navigating to {url}, type: {type(url)}")
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            print(f"Current URL: {await page.url()}")  # Debug redirect
            await asyncio.sleep(10)  # Initial wait

            while True:
                print(f"Scraping page {page_num}...")
                # Scroll to trigger lazy loading
                for _ in range(3):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(2)
                await page.wait_for_load_state("networkidle")

                # Wait for reviews with extended timeout
                await page.wait_for_selector(".review-text-content span", state="visible", timeout=30000)
                review_elements = await page.query_selector_all(".review-text-content span")
                if not review_elements:
                    print("Trying alternative selector: .a-expander-content")
                    review_elements = await page.query_selector_all(".a-expander-content")
                for elem in review_elements:
                    text = await elem.inner_text()
                    if text and text.strip() and text not in reviews:
                        reviews.append(text.strip())
                        print(f"Collected review {len(reviews)}")

                # Check for next page with fallback
                next_button = await page.query_selector("li.a-last a")
                if not next_button:
                    next_button = await page.query_selector(".a-pagination .a-last a")
                if next_button and await next_button.is_visible() and await next_button.is_enabled():
                    await next_button.click()
                    await page.wait_for_load_state("networkidle")
                    page_num += 1
                    await asyncio.sleep(random.uniform(2, 7))
                else:
                    print("No more pages found or button not accessible.")
                    break

                # Optional: Print page HTML snippet for debug
                html_snippet = await page.content()[:500]  # First 500 chars
                print(f"Page {page_num} HTML snippet: {html_snippet}")

        except PlaywrightTimeoutError as e:
            print(f"Timeout occurred: {e}. Possibly blocked or content not loading.")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            input("Press Enter to close the browser...")  # Keep open for inspection
            await browser.close()

    print(f"Total reviews extracted: {len(reviews)}")
    return reviews

# Run the test
if __name__ == "__main__":
    test_url = "https://www.amazon.in/product-reviews/B0067H6G26/ref=cm_cr_dp_d_show_all_btm?ie=UTF8&reviewerType=all_reviews"
    reviews = asyncio.run(scrape_reviews(test_url))
    with open("reviews.txt", "w", encoding="utf-8") as f:
        for i, review in enumerate(reviews, 1):
            f.write(f"Review {i}: {review}\n\n")